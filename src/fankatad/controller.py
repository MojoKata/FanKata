"""The control loop: reads sensors, applies Curves, runs Speed pulses, restores defaults."""

from __future__ import annotations

import collections
import json
import logging
import os
import tempfile
import threading
import time

from fankata_core import __version__
from fankata_core import config as cfgmod
from fankata_core import curve as curvemod
from fankata_core import expr as exprmod
from fankata_core.config import Config

from .backends import Backend, BackendError
from .backends.hwmon import HwmonBackend
from .pulse import ABORT_TEMP, Pulse

log = logging.getLogger("fankatad")

ALIAS_ORDER = ("sys.cpu", "sys.gpu", "sys.nvme", "sys.coolant")
SAMPLE_INTERVAL = 1.0      # probe history: one sample per second (requirement 7.2)
HISTORY_LEN = 120          # two minutes, handed to a GUI when it connects


def _write_json(path: str, data) -> None:
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


def _read_json(path: str, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


class Controller:
    def __init__(self, backend: Backend | str, config_path: str, run_dir: str):
        # a string is a sysfs root, for the Linux backend (and the tests)
        self.hw = HwmonBackend(backend) if isinstance(backend, str) else backend
        self.config_path = config_path
        self.run_dir = run_dir
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.inv = self.hw.inv
        self.cfg = self._load_config()
        self.originals: dict[str, dict] = _read_json(self._run("original.json"), {})
        self.touched: set[str] = set(_read_json(self._run("touched.json"), []))
        self.controlled: set[str] = set(self.touched)
        self.status: dict[str, tuple[str, str]] = {}
        self.pulse: Pulse | None = None
        self.last_pulse: dict | None = None
        self.last_restore: dict[str, dict] = {}
        self.temps: dict[str, float | None] = {}
        self.rpms: dict[str, int | None] = {}
        self.probe_vals: dict[str, tuple[float | None, str | None]] = {}
        self._interp: dict[tuple, curvemod.Interpolator] = {}
        self.history: dict[str, collections.deque] = {}
        self.sample_seq = 0
        self._last_sample = float("-inf")
        self.capture_originals()

    # --- files -----------------------------------------------------------------
    def _run(self, name: str) -> str:
        return os.path.join(self.run_dir, name)

    def _load_config(self) -> Config:
        try:
            cfg = cfgmod.load(self.config_path)
        except FileNotFoundError:
            cfg = cfgmod.default_config()
            try:
                cfgmod.save(cfg, self.config_path)
                log.info("created default configuration at %s", self.config_path)
            except OSError as e:
                log.warning("can't write %s: %s", self.config_path, e)
            return cfg
        except Exception as e:  # malformed file: keep running with defaults, don't overwrite it
            log.error("can't read %s (%s); using built-in defaults until it is fixed", self.config_path, e)
            return cfgmod.default_config()
        for err in cfgmod.validate(cfg, self.inv.probe_names, strict=False):
            log.warning("config: %s", err)
        return cfg

    def capture_originals(self) -> None:
        """Record each channel's default state before our first write (requirement 8.1)."""
        changed = False
        for pid in self.inv.pwms:
            if pid not in self.originals:
                self.originals[pid] = self.hw.capture(pid)
                changed = True
        if changed:
            _write_json(self._run("original.json"), self.originals)

    def _save_touched(self) -> None:
        _write_json(self._run("touched.json"), sorted(self.touched))

    # --- hardware --------------------------------------------------------------
    def _take_control(self, pid: str) -> str | None:
        self.last_restore.pop(pid, None)
        if pid not in self.touched:
            self.touched.add(pid)
            self._save_touched()
        self.controlled.add(pid)
        try:
            self.hw.take_control(pid)
        except BackendError as e:
            return str(e)
        return None

    def _set_duty(self, pid: str, duty: float) -> str | None:
        err = self._take_control(pid)
        try:
            self.hw.write_duty(pid, duty)
        except BackendError as e:
            return str(e)
        return err

    def restore_mode(self, pid: str) -> dict:
        """How this channel returns to its default (shown in the GUI, requirement 5.4.6)."""
        return self.hw.restore_mode(pid, self.originals.get(pid, {}))

    def restore(self, pid: str) -> dict:
        """Return one channel to its default state (requirement 8.3)."""
        self.controlled.discard(pid)
        if pid not in self.inv.pwms:
            self.touched.discard(pid)
            return {"ok": False, "message": "Device is gone."}
        try:
            result = self.hw.restore(pid, self.originals.get(pid, {}))
        except BackendError as e:
            result = {"ok": False, "message": str(e)}
        if pid in self.touched:
            self.touched.discard(pid)
            self._save_touched()
        log.info("restored %s: %s", pid, result["message"] or "ok")
        self.last_restore[pid] = result
        return result

    def restore_all(self) -> None:
        with self.lock:
            self.pulse = None
            for pid in sorted(self.touched | self.controlled):
                self.restore(pid)

    # --- the loop --------------------------------------------------------------
    def _interpolator(self, c: cfgmod.CurveDef) -> curvemod.Interpolator:
        key = (c.name, tuple(map(tuple, c.points)))
        f = self._interp.get(key)
        if f is None:
            if len(self._interp) > 64:
                self._interp.clear()
            f = self._interp[key] = curvemod.Interpolator(c.points)
        return f

    def interval(self) -> float:
        return 0.25 if self.pulse else 1.0

    def tick(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self.lock:
            self.hw.refresh()
            self.temps = self.hw.read_temps()
            self.rpms = self.hw.read_rpms()
            probes = exprmod.ProbeSet(self.temps, {p.name: p.expr for p in self.cfg.probes})
            self.probe_vals = {name: probes.try_value(name)
                               for name in list(self.temps) + [p.name for p in self.cfg.probes]}
            self._record_sample(now)
            self._tick_pulse(now)
            for pid, ch in self.inv.pwms.items():
                if self.pulse and self.pulse.fan == pid:
                    continue
                s = self.cfg.fan(pid)
                c = self.cfg.curve(s.curve) if s.curve else None
                if c and s.probe:
                    val, err = self.probe_vals.get(s.probe) or (None, f"Unknown probe “{s.probe}”.")
                    if val is None:
                        duty = 100.0
                        status = ("warning", f"{s.probe} can’t be evaluated ({err}) — running at 100 %.")
                    else:
                        duty = self._interpolator(c)(val)
                        status = ("managed", "")
                    hw_err = self._set_duty(pid, duty)
                    self.status[pid] = ("warning", hw_err) if hw_err else status
                else:
                    if pid in self.controlled or pid in self.touched:
                        self.restore(pid)
                    lr = self.last_restore.get(pid)
                    if c and not s.probe:
                        self.status[pid] = ("warning", "Choose a probe to control this fan with its curve.")
                    elif lr and not lr["ok"]:
                        self.status[pid] = ("warning", lr["message"])
                    else:
                        self.status[pid] = ("default", "")

    def _record_sample(self, now: float) -> None:
        """Probe history at a steady 1 Hz, even when ticks run faster (Speed pulse)."""
        if now - self._last_sample < SAMPLE_INTERVAL * 0.95:
            return
        self._last_sample = now
        self.sample_seq += 1
        for name, (v, _) in self.probe_vals.items():
            h = self.history.get(name)
            if h is None:
                h = self.history[name] = collections.deque(maxlen=HISTORY_LEN)
            h.append(None if v is None else round(v, 2))
        for gone in set(self.history) - set(self.probe_vals):
            del self.history[gone]

    def _tick_pulse(self, now: float) -> None:
        p = self.pulse
        if not p:
            return
        pid = p.fan
        if pid not in self.inv.pwms:
            self.pulse = None
            return
        s = self.cfg.fan(pid)
        for probe in [s.probe, "sys.cpu"]:
            if not probe:
                continue
            v = self.probe_vals.get(probe, (None, None))[0]
            if v is not None and v > ABORT_TEMP and p.stop_reason is None:
                p.stop_reason = f"Stopped early: {probe} reached {v:.0f} °C."
        if p.finished(now):
            if p.stop_reason is None:
                p.stop_reason = "done"
            self.last_pulse = {**p.analyze(), **p.snapshot(now)}
            self.pulse = None
            log.info("speed pulse on %s finished: %s", pid, self.last_pulse["message"])
            s = self.cfg.fan(pid)
            if not (s.curve and s.probe and self.cfg.curve(s.curve)):
                self.restore(pid)
            return
        duty = p.duty_at(p.elapsed(now))
        err = self._set_duty(pid, duty)
        self.status[pid] = ("warning", err) if err else ("pulse", "")
        p.record(now, duty, self.rpms)

    # --- commands --------------------------------------------------------------
    def set_config(self, data: dict) -> list[str]:
        try:
            new = Config.from_dict(data)
        except (KeyError, TypeError, ValueError) as e:
            return [f"Malformed configuration: {e}"]
        errs = cfgmod.validate(new, self.inv.probe_names, strict=True)
        if errs:
            return errs
        with self.lock:
            try:
                cfgmod.save(new, self.config_path)
            except OSError as e:
                return [f"Can’t save the configuration: {e.strerror or e}."]
            self.cfg = new
        self.wake.set()
        return []

    def start_pulse(self, pid: str) -> str | None:
        with self.lock:
            ch = self.inv.pwms.get(pid)
            if not ch:
                return f"Unknown fan “{pid}”."
            s = self.cfg.fan(pid)
            prev = self.pulse
            if prev and prev.fan != pid:
                prev.stop_reason = "Stopped: another speed pulse started."
                self.last_pulse = {**prev.analyze(), **prev.snapshot(now := time.monotonic())}
                if not (self.cfg.fan(prev.fan).curve and self.cfg.fan(prev.fan).probe):
                    self.restore(prev.fan)
            now = time.monotonic()
            self.pulse = Pulse.create(pid, s.rpm_sensor or ch.tach_id, s.type or ch.detected_type,
                                      self.hw.read_duty(pid), now)
            self.last_pulse = None
            self._tick_pulse(now)
        self.wake.set()
        return None

    def stop_pulse(self) -> None:
        with self.lock:
            if self.pulse:
                self.pulse.stop_reason = "Stopped."
        self.wake.set()

    # --- state for the GUI -----------------------------------------------------
    def state(self, include_history: bool = False) -> dict:
        """include_history: the recent probe samples, sent when a GUI first connects."""
        now = time.monotonic()
        with self.lock:
            fans = []
            for pid, ch in self.inv.pwms.items():
                s = self.cfg.fan(pid)
                tach = s.rpm_sensor if s.rpm_sensor in self.inv.tachs else ch.tach_id
                status, message = self.status.get(pid, ("default", ""))
                pv = self.probe_vals.get(s.probe, (None, None))[0] if s.probe else None
                fans.append({
                    "id": pid, "chip": ch.chip, "driver": ch.driver, "index": ch.index,
                    "name": s.name or ch.driver_label, "default_name": ch.driver_label,
                    "driver_label": ch.driver_label + ("" if ch.tach_id else " · no tach"),
                    "detected_type": ch.detected_type, "type": s.type or ch.detected_type,
                    "type_overridden": bool(s.type),
                    "rpm": self.rpms.get(tach) if tach else None, "rpm_sensor": tach,
                    "duty": self.hw.read_duty(pid),
                    "curve": s.curve, "probe": s.probe, "probe_value": pv,
                    "managed": status in ("managed", "pulse") or (status == "warning" and pid in self.controlled),
                    "status": status, "message": message,
                    "restore": self.restore_mode(pid),
                })
            probes = []
            names = sorted(self.temps, key=lambda n: (n not in ALIAS_ORDER,
                                                      ALIAS_ORDER.index(n) if n in ALIAS_ORDER else 0, n))
            for n in names:
                probes.append({"name": n, "kind": "system", "desc": self.inv.probe_desc(n),
                               "value": self.temps.get(n), "error": None if self.temps.get(n) is not None
                               else "Can’t be read."})
            for p in self.cfg.probes:
                v, err = self.probe_vals.get(p.name, (None, "Not evaluated yet."))
                probes.append({"name": p.name, "kind": "custom", "desc": p.expr, "expr": p.expr,
                               "value": v, "error": err})
            return {
                "service": {"version": __version__, "readonly": False, "hardware": self.hw.describe()},
                "config": self.cfg.to_dict(),
                "fans": fans,
                "probes": probes,
                "tachs": [{"id": t.id, "label": t.label, "rpm": self.rpms.get(t.id)} for t in self.inv.tachs.values()],
                "pulse": self.pulse.snapshot(now) if self.pulse else None,
                "last_pulse": self.last_pulse,
                "sample": {"seq": self.sample_seq, "interval": SAMPLE_INTERVAL},
                **({"history": {k: list(v) for k, v in self.history.items()}} if include_history else {}),
            }


def restore_from_files(backend: Backend | str, run_dir: str) -> int:
    """`fankatad --restore`, run by ExecStopPost even after a crash (requirement 8.4)."""
    originals = _read_json(os.path.join(run_dir, "original.json"), None)
    touched = _read_json(os.path.join(run_dir, "touched.json"), [])
    if not originals or not touched:
        return 0
    ctl = Controller.__new__(Controller)
    ctl.hw = HwmonBackend(backend) if isinstance(backend, str) else backend
    ctl.run_dir = run_dir
    ctl.lock = threading.RLock()
    ctl.inv = ctl.hw.inv
    ctl.originals, ctl.touched, ctl.controlled = originals, set(touched), set(touched)
    ctl.last_restore = {}
    failed = 0
    for pid in sorted(ctl.touched.copy()):
        if not ctl.restore(pid)["ok"]:
            failed += 1
    return 1 if failed else 0
