"""The QML-facing backend: live state, edits, and validation using fankata_core.

Edits are applied to a local copy of the configuration straight away (so the
UI responds instantly), checked with the same rules the service uses, then
sent to the service, which validates again and is the one that saves.
"""

from __future__ import annotations

import collections
import os
import re

from PySide6.QtCore import Property, QObject, QProcess, QTimer, Signal, Slot

from fankata_core import config as cfgmod
from fankata_core import curve as curvemod
from fankata_core import expr as exprmod
from fankata_core.config import Config, CurveDef, FanSettings, ProbeDef

from . import prefs as prefsmod
from .client import ServiceClient
from .readonly import ReadOnlyPoller

SERVICECTL = "/opt/fankata/bin/fankata-servicectl"     # Linux: run through pkexec
HISTORY = 120       # samples (1 per second), matching the service's history
TYPE_LABELS = {"case": "Case fan", "aio": "AIO cooler fan", "pump": "Pump", "generic": "Generic PWM header"}


def _fmt(v: float) -> str:
    return f"{v:g}"


class Backend(QObject):
    changed = Signal()
    connectionChanged = Signal()
    serviceBusyChanged = Signal()
    prefsChanged = Signal()
    toast = Signal(str, str)          # kind ("error" | "info"), message

    def __init__(self, socket_path: str, sysfs_root: str, config_path: str, parent=None):
        super().__init__(parent)
        self._state: dict = {"fans": [], "probes": [], "config": Config().to_dict(), "pulse": None,
                             "last_pulse": None, "service": {"readonly": True}}
        self._cfg = Config()
        self._pending = 0
        self._history: dict[str, collections.deque] = {}
        self._last_seq = None
        self._prefs = prefsmod.load()
        self._dismissed_pulse = None
        self._cache: dict[str, object] = {}
        self.poller = ReadOnlyPoller(sysfs_root, config_path)
        self.client = ServiceClient(socket_path, self)
        self.client.stateEvent.connect(self._on_state)
        self.client.connected.connect(self.connectionChanged)
        self.client.disconnected.connect(self._on_disconnected)
        self._service_target = None          # True/False while turning the service on/off
        self.service_timer = QTimer(self, interval=30000, singleShot=True)
        self.service_timer.timeout.connect(self._service_timeout)
        self.client.connected.connect(self._service_settled)
        self.client.disconnected.connect(self._service_settled)
        self.ro_timer = QTimer(self, interval=1000)
        self.ro_timer.timeout.connect(self._poll_readonly)
        self.client.connect_now()
        QTimer.singleShot(1200, self._maybe_readonly)

    # --- incoming state ----------------------------------------------------------
    def _on_state(self, state: dict) -> None:
        self.ro_timer.stop()
        self._apply(state)

    def _apply(self, state: dict) -> None:
        self._state = state
        if self._pending == 0:
            self._cfg = Config.from_dict(state.get("config") or {})
        sample = (state.get("sample") or {}).get("seq")
        if "history" in state:
            # a fresh connection: the service's recent samples replace ours
            self._history = {k: collections.deque(v, maxlen=HISTORY) for k, v in state["history"].items()}
            self._last_seq = sample
        elif sample is not None and sample != self._last_seq:
            # one point per service sample (1 per second), never for command replies
            self._last_seq = sample
            for p in state.get("probes", []):
                self._history.setdefault(p["name"], collections.deque(maxlen=HISTORY)).append(p["value"])
        self._rebuild()

    def _on_disconnected(self) -> None:
        self._pending = 0
        self.connectionChanged.emit()
        self._maybe_readonly()

    def _maybe_readonly(self) -> None:
        if not self.client.is_connected and not self.ro_timer.isActive():
            self._poll_readonly()
            self.ro_timer.start()

    def _poll_readonly(self) -> None:
        if self.client.is_connected:
            self.ro_timer.stop()
            return
        self._apply(self.poller.state())

    def _rebuild(self) -> None:
        self._cache.clear()
        self.changed.emit()

    # --- properties --------------------------------------------------------------
    def _get_connected(self) -> bool:
        return self.client.is_connected

    connected = Property(bool, _get_connected, notify=connectionChanged)

    def _get_readonly(self) -> bool:
        return not self.client.is_connected

    readOnly = Property(bool, _get_readonly, notify=connectionChanged)

    # --- turning the service on and off (requirement 4.6) -------------------------------
    def _get_service_busy(self) -> bool:
        return self._service_target is not None

    serviceBusy = Property(bool, _get_service_busy, notify=serviceBusyChanged)

    def _set_service_target(self, target) -> None:
        self._service_target = target
        if target is None:
            self.service_timer.stop()
        else:
            self.service_timer.start()
        self.serviceBusyChanged.emit()

    def _service_settled(self) -> None:
        if self._service_target is not None and self._service_target == self.client.is_connected:
            on = self._service_target
            self._set_service_target(None)
            self.toast.emit("info", "Fan control is on." if on else
                            "Fan control is off. Every fan is back under firmware control.")

    def _service_timeout(self) -> None:
        on = self._service_target
        self._set_service_target(None)
        self.toast.emit("error", f"The service didn’t {'start' if on else 'stop'} in time.")

    def _service_failed(self, message: str) -> None:
        self._set_service_target(None)
        self.toast.emit("error", message)

    @Slot(bool)
    def setServiceEnabled(self, on: bool) -> None:
        if self._service_target is not None or on == self.client.is_connected:
            return
        self._set_service_target(on)
        override = os.environ.get("FANKATA_SERVICECTL")      # tests and demos
        if override:
            self._run([override, "enable" if on else "disable"], on)
        elif os.name == "nt":
            if on:
                # the installer lets signed-in users start this service (requirement 1.12.12)
                self._run(["sc.exe", "start", "fankatad"], on)
            else:
                def done(r: dict) -> None:
                    if not r.get("ok"):
                        self._service_failed(r.get("error") or "Couldn’t turn the service off.")
                self.client.request("service_disable", done)
        else:
            if not os.path.exists(SERVICECTL):
                self._service_failed("Turning the service on or off needs the installed Fankata package.")
                return
            self._run(["pkexec", SERVICECTL, "enable" if on else "disable"], on)

    def _run(self, argv: list[str], on: bool) -> None:
        p = QProcess(self)
        p.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        handled = []

        def finished(code, _status) -> None:
            if handled:
                return
            handled.append(1)
            try:
                out = bytes(p.readAll()).decode(errors="replace").strip()
            except RuntimeError:         # destroyed while the app is shutting down
                return
            if code == 0 or (os.name == "nt" and code == 1056):      # 1056: already running
                pass              # wait for the connection to come up / go away
            elif code in (126, 127) and argv[0] == "pkexec":
                self._service_failed("Not authorized to turn the service " + ("on." if on else "off."))
            else:
                self._service_failed(f"Couldn’t turn the service {'on' if on else 'off'}"
                                     + (f": {out.splitlines()[-1]}" if out else f" (exit code {code})."))
            p.deleteLater()

        def failed(error) -> None:
            if handled or error != QProcess.ProcessError.FailedToStart:
                return
            handled.append(1)
            self._service_failed(f"Couldn’t run {argv[0]}.")
            p.deleteLater()

        p.finished.connect(finished)
        p.errorOccurred.connect(failed)
        p.start(argv[0], argv[1:])

    @Slot()
    def rescanHardware(self) -> None:
        self.poller.rescan()
        if not self.client.is_connected:
            self._poll_readonly()

    def _get_hardware(self) -> str:
        return (self._state.get("service") or {}).get("hardware") or ""

    hardware = Property(str, _get_hardware, notify=changed)

    def _system_probe_names(self) -> frozenset[str]:
        return frozenset(p["name"] for p in self._state.get("probes", []) if p["kind"] == "system")

    def _curve_users(self) -> dict[str, list[str]]:
        names = {f["id"]: f["name"] for f in self._state.get("fans", [])}
        users: dict[str, list[str]] = {}
        for fid, s in self._cfg.fans.items():
            if s.curve:
                users.setdefault(s.curve, []).append(s.name or names.get(fid, fid))
        return users

    def _get_fans(self) -> list:
        if "fans" not in self._cache:
            out = []
            probes = {p["name"]: p for p in self._state.get("probes", [])}
            pulse = self._state.get("pulse")
            for f in self._state.get("fans", []):
                s = self._cfg.fan(f["id"])
                d = dict(f)
                d["name"] = s.name or f["default_name"]
                d["curve"] = s.curve
                d["probe"] = s.probe
                d["type"] = s.type or f["detected_type"]
                d["type_overridden"] = bool(s.type)
                c = self._cfg.curve(s.curve) if s.curve else None
                d["curve_points"] = c.points if c else []
                d["curve_allow_zero"] = bool(c and c.allow_zero)
                pv = probes.get(s.probe, {}).get("value") if s.probe else None
                d["probe_value"] = pv
                d["pulsing"] = bool(pulse and pulse.get("fan") == f["id"])
                d["type_label"] = TYPE_LABELS.get(d["type"], d["type"])
                if not s.curve and f["managed"] and not d["pulsing"]:
                    # cleared locally; the service hasn't confirmed the restore yet (requirement 5.4.2)
                    d["status"], d["managed"] = "restoring", False
                out.append(d)
            self._cache["fans"] = out
        return self._cache["fans"]

    fans = Property("QVariantList", _get_fans, notify=changed)

    def _get_curves(self) -> list:
        if "curves" not in self._cache:
            users = self._curve_users()
            self._cache["curves"] = [{"name": c.name, "points": c.points, "allowZero": c.allow_zero,
                                      "users": users.get(c.name, [])} for c in self._cfg.curves]
        return self._cache["curves"]

    curves = Property("QVariantList", _get_curves, notify=changed)

    def _get_probes(self) -> list:
        if "probes" not in self._cache:
            out = []
            for p in self._state.get("probes", []):
                d = dict(p)
                if p["kind"] == "custom":
                    pd = self._cfg.probe(p["name"])
                    if pd:
                        d["expr"] = d["desc"] = pd.expr
                d["history"] = list(self._history.get(p["name"], []))   # None = no reading at that second
                d["users"] = cfgmod.users_of_probe(self._cfg, p["name"])
                out.append(d)
            # custom probes added locally but not yet echoed by the service
            known = {p["name"] for p in out}
            for pd in self._cfg.probes:
                if pd.name not in known:
                    v, err = self._eval(pd.expr)
                    out.append({"name": pd.name, "kind": "custom", "desc": pd.expr, "expr": pd.expr,
                                "value": v, "error": err, "history": [], "users": []})
            self._cache["probes"] = out
        return self._cache["probes"]

    probes = Property("QVariantList", _get_probes, notify=changed)

    def _get_pulse(self):
        return self._state.get("pulse")

    pulse = Property("QVariant", _get_pulse, notify=changed)

    def _get_last_pulse(self):
        lp = self._state.get("last_pulse")
        if lp and lp == self._dismissed_pulse:
            return None
        return lp

    lastPulse = Property("QVariant", _get_last_pulse, notify=changed)

    def _get_prefs(self) -> dict:
        return dict(self._prefs)

    prefs = Property("QVariantMap", _get_prefs, notify=prefsChanged)

    @Slot(str, "QVariant")
    def setPref(self, key: str, value) -> None:
        if hasattr(value, "toVariant"):      # JS arrays/objects arrive as QJSValue
            value = value.toVariant()
        if self._prefs.get(key) != value:
            self._prefs[key] = value
            prefsmod.save(self._prefs)
            self.prefsChanged.emit()

    # --- committing ----------------------------------------------------------------
    def _commit(self, cfg: Config) -> str:
        if not self.client.is_connected:
            return "The Fankata service isn’t running, so changes can’t be saved."
        errs = cfgmod.validate(cfg, self._system_probe_names(), strict=True)
        if errs:
            return errs[0]
        self._cfg = cfg
        self._pending += 1
        self._rebuild()

        def done(r: dict) -> None:
            self._pending = max(0, self._pending - 1)
            if r.get("ok"):
                if r.get("result"):
                    self._apply(r["result"])
            else:
                self.toast.emit("error", r.get("error") or "The change was not applied.")
                if self._pending == 0:
                    self._cfg = Config.from_dict(self._state.get("config") or {})
                    self._rebuild()

        self.client.request("set_config", done, config=cfg.to_dict())
        return ""

    def _edit(self) -> Config:
        return self._cfg.copy()

    # --- curves ---------------------------------------------------------------------
    @Slot("QVariantList", result="QVariantList")
    def curveSamples(self, points) -> list:
        try:
            return curvemod.sample([[float(p[0]), float(p[1])] for p in points])
        except (ValueError, TypeError, IndexError, ZeroDivisionError):
            return []

    @Slot("QVariantList", float, result=float)
    def curveValue(self, points, x: float) -> float:
        try:
            return curvemod.evaluate([[float(p[0]), float(p[1])] for p in points], x)
        except (ValueError, TypeError, IndexError, ZeroDivisionError):
            return 0.0

    @Slot(str, float, float, result=str)
    def addPointReason(self, name: str, x: float, y: float) -> str:
        c = self._cfg.curve(name)
        if not c:
            return "Unknown curve."
        return curvemod.add_point_reason(c.points, x, y, c.allow_zero) or ""

    @Slot(str, float, result="QVariantList")
    def validBand(self, name: str, x: float) -> list:
        c = self._cfg.curve(name)
        return list(curvemod.valid_band(c.points, x, c.allow_zero)) if c else [0, 100]

    @Slot(str, float, float, result=str)
    def addPoint(self, name: str, x: float, y: float) -> str:
        cfg = self._edit()
        c = cfg.curve(name)
        if not c:
            return "Unknown curve."
        why = curvemod.add_point_reason(c.points, x, y, c.allow_zero)
        if why:
            return why
        c.points = sorted(c.points + [[x, y]])
        return self._commit(cfg)

    @Slot(str, int, result=str)
    def removePoint(self, name: str, index: int) -> str:
        cfg = self._edit()
        c = cfg.curve(name)
        if not c or not (0 <= index < len(c.points)):
            return "Unknown point."
        if len(c.points) <= curvemod.MIN_POINTS:
            return "A curve needs at least two points."
        del c.points[index]
        return self._commit(cfg)

    @Slot(str, int, str, str, result=str)
    def setPoint(self, name: str, index: int, xs: str, ys: str) -> str:
        cfg = self._edit()
        c = cfg.curve(name)
        if not c or not (0 <= index < len(c.points)):
            return "Unknown point."
        try:
            x = float(xs.replace("°C", "").replace("°", "").strip())
            y = float(ys.replace("%", "").strip())
        except ValueError:
            return "Enter numbers only."
        c.points[index] = [x, y]
        errs = curvemod.point_errors(c.points, c.allow_zero)
        if errs:
            return errs[0][1]
        return self._commit(cfg)

    def _unique_curve_name(self, base: str) -> str:
        names = {c.name for c in self._cfg.curves}
        if base not in names:
            return base
        i = 2
        while f"{base} {i}" in names:
            i += 1
        return f"{base} {i}"

    @Slot(result=str)
    def newCurve(self) -> str:
        cfg = self._edit()
        name = self._unique_curve_name("New curve")
        cfg.curves.append(CurveDef(name, [[30, 30], [60, 50], [80, 100]]))
        err = self._commit(cfg)
        if err:
            self.toast.emit("error", err)
            return ""
        return name

    @Slot(str, result=str)
    def duplicateCurve(self, name: str) -> str:
        cfg = self._edit()
        c = cfg.curve(name)
        if not c:
            return ""
        new = self._unique_curve_name(f"{name} copy")
        cfg.curves.insert(cfg.curves.index(c) + 1, CurveDef(new, [list(p) for p in c.points], c.allow_zero))
        err = self._commit(cfg)
        if err:
            self.toast.emit("error", err)
            return ""
        return new

    @Slot(str, str, result=str)
    def renameCurve(self, old: str, new: str) -> str:
        new = new.strip()
        if new == old:
            return ""
        if not new:
            return "Curve names can’t be empty."
        if self._cfg.curve(new):
            return f"There is already a curve named “{new}”."
        cfg = self._edit()
        cfg.curve(old).name = new
        for s in cfg.fans.values():
            if s.curve == old:
                s.curve = new
        return self._commit(cfg)

    @Slot(str, result=str)
    def deleteCurve(self, name: str) -> str:
        users = self._curve_users().get(name)
        if users:
            return f"Used by {', '.join(users)}."
        cfg = self._edit()
        cfg.curves = [c for c in cfg.curves if c.name != name]
        return self._commit(cfg)

    @Slot(str, bool, result=str)
    def setAllowZero(self, name: str, on: bool) -> str:
        cfg = self._edit()
        c = cfg.curve(name)
        if not c:
            return "Unknown curve."
        c.allow_zero = on
        if not on:
            c.points = curvemod.raise_to_floor(c.points)
        return self._commit(cfg)

    # --- fans ------------------------------------------------------------------------
    def _fan_edit(self, fid: str) -> tuple[Config, FanSettings]:
        cfg = self._edit()
        s = cfg.fans.get(fid)
        if s is None:
            s = cfg.fans[fid] = FanSettings()
        return cfg, s

    def _default_probe(self, fid: str) -> str | None:
        fan = next((f for f in self._state.get("fans", []) if f["id"] == fid), None)
        names = self._system_probe_names()
        typ = (self._cfg.fan(fid).type or (fan or {}).get("detected_type"))
        for cand in (["sys.coolant", "sys.cpu"] if typ in ("aio", "pump") else ["sys.cpu"]):
            if cand in names:
                return cand
        return None

    @Slot(str, str, result=str)
    def setFanCurve(self, fid: str, curve: str) -> str:
        cfg, s = self._fan_edit(fid)
        s.curve = curve or None
        if s.curve and not s.probe:
            s.probe = self._default_probe(fid)
        return self._commit(cfg)

    @Slot(str, str, str, result=str)
    def setFanAssignment(self, fid: str, curve: str, probe: str) -> str:
        """Curve and Probe in one change (used when a fan is dropped into a Probe group)."""
        cfg, s = self._fan_edit(fid)
        s.curve = curve or None
        s.probe = probe or None
        return self._commit(cfg)

    @Slot(str, str, result=str)
    def setFanProbe(self, fid: str, probe: str) -> str:
        cfg, s = self._fan_edit(fid)
        s.probe = probe or None
        return self._commit(cfg)

    @Slot(str, str, result=str)
    def renameFan(self, fid: str, name: str) -> str:
        cfg, s = self._fan_edit(fid)
        fan = next((f for f in self._state.get("fans", []) if f["id"] == fid), {})
        name = name.strip()
        s.name = None if not name or name == fan.get("default_name") else name
        return self._commit(cfg)

    @Slot(str, str, result=str)
    def setFanType(self, fid: str, typ: str) -> str:
        cfg, s = self._fan_edit(fid)
        fan = next((f for f in self._state.get("fans", []) if f["id"] == fid), {})
        s.type = None if not typ or typ == fan.get("detected_type") else typ
        return self._commit(cfg)

    @Slot(str)
    def startPulse(self, fid: str) -> None:
        self._dismissed_pulse = None

        def done(r: dict) -> None:
            if not r.get("ok"):
                self.toast.emit("error", r.get("error") or "Couldn’t start the speed pulse.")
            elif r.get("result"):
                self._apply(r["result"])

        if not self.client.is_connected:
            self.toast.emit("error", "The Fankata service isn’t running.")
            return
        self.client.request("pulse_start", done, fan=fid)

    @Slot()
    def stopPulse(self) -> None:
        self.client.request("pulse_stop", lambda r: None)

    @Slot()
    def dismissPulseResult(self) -> None:
        self._dismissed_pulse = self._state.get("last_pulse")
        self._rebuild()

    # --- probes -----------------------------------------------------------------------
    def _values(self) -> dict[str, float | None]:
        return {p["name"]: p["value"] for p in self._state.get("probes", []) if p["kind"] == "system"}

    def _eval(self, src: str, extra: dict[str, str] | None = None) -> tuple[float | None, str | None]:
        custom = {p.name: p.expr for p in self._cfg.probes}
        custom.update(extra or {})
        ps = exprmod.ProbeSet(self._values(), custom)
        key = "\0expr"
        ps.custom[key] = src
        try:
            ps._asts[key] = exprmod.parse(src)
        except exprmod.ExprError as e:
            return None, e.message
        return ps.try_value(key)

    @Slot(str, str, str, result="QVariantMap")
    def checkProbe(self, original: str, name: str, src: str) -> dict:
        out: dict = {"nameOk": True, "nameError": "", "exprOk": False, "error": "", "pos": -1, "length": 0,
                     "suggestion": "", "value": None, "formula": "", "tokens": self._tokens(src)}
        if not exprmod.is_valid_custom_name(name):
            out["nameOk"] = False
            out["nameError"] = ("Enter a name." if not name else
                                "Start with a letter, then use letters, digits and _ only.")
        elif name != original and self._cfg.probe(name):
            out["nameOk"] = False
            out["nameError"] = f"There is already a probe named “{name}”."
        known = set(self._values()) | {p.name for p in self._cfg.probes if p.name != original} | ({name} if name else set())
        try:
            ast, names = exprmod.check(src, known)
        except exprmod.ExprError as e:
            out.update(error=e.message, pos=e.pos, length=e.length, suggestion=e.suggestion or "")
            return out
        graph = {p.name: [] for p in self._cfg.probes if p.name != original}
        for p in self._cfg.probes:
            if p.name == original:
                continue
            try:
                graph[p.name] = [n for n, _ in exprmod.refs(exprmod.parse(p.expr))]
            except exprmod.ExprError:
                pass
        graph[name or "\0new"] = names
        cycle = exprmod.find_cycle(graph)
        if cycle:
            out["error"] = "Probes can’t reference themselves: " + " → ".join(cycle) + "."
            return out
        v, err = self._eval(src, {} if not original else {original: src})
        out["exprOk"] = True
        out["value"] = v
        out["error"] = err or ""
        out["formula"] = self._formula(src)
        return out

    def _tokens(self, src: str) -> list:
        toks, i = [], 0
        pat = re.compile(r"\s+|\d+\.?\d*|\.\d+|[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]*)?|[-+*/^()]|.")
        known = set(self._values()) | {p.name for p in self._cfg.probes}
        for m in pat.finditer(src):
            t = m.group()
            if t.isspace():
                kind = "space"
            elif re.fullmatch(r"\d+\.?\d*|\.\d+", t):
                kind = "number"
            elif re.fullmatch(r"[-+*/^()]", t):
                kind = "op"
            elif re.fullmatch(r"[A-Za-z_].*", t):
                kind = "probe" if t in known else "name"
            else:
                kind = "bad"
            toks.append({"text": t, "kind": kind, "pos": m.start()})
            i = m.end()
        return toks

    def _formula(self, src: str) -> str:
        vals = self._values()
        custom = {p.name for p in self._cfg.probes}
        parts = []
        for t in self._tokens(src):
            if t["kind"] == "space":
                continue
            if t["kind"] in ("probe", "name"):
                v = vals.get(t["text"])
                if v is None and t["text"] in custom:
                    v, _ = self._eval(t["text"])
                parts.append(f"{v:.1f}" if v is not None else "?")
            elif t["kind"] == "number":
                parts.append(_fmt(float(t["text"])))
            else:
                parts.append({"*": "×", "/": "/", "-": "−"}.get(t["text"], t["text"]))
        s = " ".join(parts).replace("( ", "(").replace(" )", ")")
        return "= " + s

    @Slot(str, result="QVariantList")
    def expressionHistory(self, src: str) -> list:
        try:
            ast = exprmod.parse(src)
        except exprmod.ExprError:
            return []
        names = {n for n, _ in exprmod.refs(ast)}
        custom = {p.name: p.expr for p in self._cfg.probes}
        sys_hist = {k: h for k, h in self._history.items() if k.startswith(exprmod.SYS_PREFIX)}
        n = min((len(sys_hist[k]) for k in names if k in sys_hist), default=0)
        out = []
        for i in range(-n, 0):
            sysvals = {k: (h[i] if len(h) >= -i else None) for k, h in sys_hist.items()}
            ps = exprmod.ProbeSet(sysvals, custom)
            ps.custom["\0"] = src
            ps._asts["\0"] = ast
            out.append(ps.try_value("\0")[0])      # None where a reading was missing
        return out

    @Slot(str, str, str, result=str)
    def saveProbe(self, original: str, name: str, src: str) -> str:
        chk = self.checkProbe(original, name, src)
        if not chk["nameOk"]:
            return chk["nameError"]
        if not chk["exprOk"]:
            return chk["error"]
        cfg = self._edit()
        if original:
            p = cfg.probe(original)
            if not p:
                return "Unknown probe."
            p.name, p.expr = name, src
            if name != original:
                for q in cfg.probes:
                    q.expr = self._rename_ref(q.expr, original, name)
                for s in cfg.fans.values():
                    if s.probe == original:
                        s.probe = name
        else:
            cfg.probes.append(ProbeDef(name, src))
        return self._commit(cfg)

    @staticmethod
    def _rename_ref(src: str, old: str, new: str) -> str:
        try:
            toks = exprmod.tokenize(src)
        except exprmod.ExprError:
            return src
        out, last = [], 0
        for t in toks:
            if t.kind == "name" and t.text == old:
                out.append(src[last:t.pos])
                out.append(new)
                last = t.pos + len(t.text)
        out.append(src[last:])
        return "".join(out)

    @Slot(str, result=str)
    def deleteProbe(self, name: str) -> str:
        users = cfgmod.users_of_probe(self._cfg, name)
        if users:
            return "Used by " + ", ".join(users) + "."
        cfg = self._edit()
        cfg.probes = [p for p in cfg.probes if p.name != name]
        return self._commit(cfg)
