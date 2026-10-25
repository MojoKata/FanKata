"""Troubleshoot fans (requirement 4.7): the dialog's state and actions.

Facts come from this PC (Linux: unprivileged reads; Windows: the service's
`diagnose` command, or local reads while the service is off). Steps that need root
on Linux run the fankata-troubleshoot helper through pkexec, which asks for an
administrator password.
"""

from __future__ import annotations

import json
import os
import sys
import threading

from PySide6.QtCore import Property, QObject, QProcess, Signal, Slot
from PySide6.QtGui import QGuiApplication

from fankata_core import hwmon
from fankata_core import troubleshoot as ts

HELPER = "/opt/fankata/bin/fankata-troubleshoot"
TIPS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tips")


class Troubleshooter(QObject):
    changed = Signal()
    busyChanged = Signal()
    grubRequested = Signal("QVariantMap")
    _factsReady = Signal(object)

    def __init__(self, backend, sysfs_root: str = "/", etc_root: str = "/etc", parent=None):
        super().__init__(parent)
        self.backend = backend
        self.root = sysfs_root
        self.etc = etc_root
        self.platform = "windows" if os.name == "nt" else "linux"
        self._facts: dict = {}
        self._scan: dict | None = None
        self._scan_raw = ""
        self._load: dict | None = None
        self._persist = True
        self._busy = ""
        self._gathering = False
        self._result: dict = {}
        self._error = ""
        self._tips_md = self._read_tips()
        self._factsReady.connect(self._on_facts)

    def _read_tips(self) -> str:
        for d in (TIPS_DIR, os.path.join(getattr(sys, "_MEIPASS", ""), "fankata", "tips")):
            try:
                with open(os.path.join(d, f"{self.platform}.md"), encoding="utf-8") as f:
                    return f.read()
            except OSError:
                continue
        return ""

    # --- properties ----------------------------------------------------------------
    def _get_result(self) -> dict:
        return self._result

    result = Property("QVariantMap", _get_result, notify=changed)

    def _get_busy(self) -> str:
        return self._busy if self._busy else ("gather" if self._gathering else "")

    busy = Property(str, _get_busy, notify=busyChanged)

    def _set_busy(self, v: str) -> None:
        self._busy = v
        self.busyChanged.emit()

    # --- facts ----------------------------------------------------------------------
    def _service(self) -> dict:
        st = self.backend._state.get("service") or {}
        return {"running": self.backend.connected, "version": st.get("version"), "hardware": st.get("hardware") or ""}

    @Slot()
    def run(self) -> None:
        """Collect facts again and rebuild the checks (opening the dialog, Run again, after an action)."""
        if self._gathering:
            return
        self._gathering = True
        self.busyChanged.emit()
        if self.platform == "windows" and self.backend.connected:
            def done(r: dict) -> None:
                facts = r.get("result") if r.get("ok") else None
                if facts is None:
                    threading.Thread(target=self._gather_local, daemon=True).start()
                else:
                    facts["service"] = {**self._service(), **(facts.get("service") or {}), "running": True}
                    self._factsReady.emit(facts)
            self.backend.client.request("diagnose", done)
            return
        threading.Thread(target=self._gather_local, daemon=True).start()

    def _gather_local(self) -> None:
        try:
            if self.platform == "windows":
                from fankata_core.winfacts import windows_facts
                facts = windows_facts(service=self._service())
            else:
                facts = ts.linux_facts(self.root, self._service(), hwmon.scan(self.root))
        except Exception as e:  # never leave the dialog spinning
            facts = {"platform": self.platform, "service": self._service(), "chips": [], "error": str(e)}
        self._factsReady.emit(facts)

    def _on_facts(self, facts: dict) -> None:
        old_log = self._facts.get("kernel_log")
        if facts.get("kernel_log") is None and old_log is not None:
            facts["kernel_log"] = old_log          # read by the helper earlier
        self._facts = facts
        self._gathering = False
        self.busyChanged.emit()
        self._rebuild()

    def _rebuild(self) -> None:
        f = self._facts
        if not f:
            return
        if f.get("platform") == "windows":
            r = ts.windows_checks(f)
        else:
            r = ts.linux_checks(f, self._scan, self._load, self._persist)
        r["tips"] = ts.markdown_blocks(self._tips_md)
        r["tips_count"] = ts.tips_count(self._tips_md)
        r["persist"] = self._persist
        r["error"] = self._error
        self._result = r
        self.changed.emit()

    @Slot(bool)
    def setPersist(self, on: bool) -> None:
        self._persist = on
        self._rebuild()

    # --- actions ----------------------------------------------------------------------
    @Slot(str)
    def act(self, action: str) -> None:
        if self._busy:
            return
        self._error = ""
        if action == "service_on":
            self.backend.setServiceEnabled(True)
        elif action == "scan":
            self._helper(action, ["scan"], self._scanned)
        elif action == "install_lm_sensors":
            self._helper(action, ["install-lm-sensors"], self._done)
        elif action.startswith("load:"):
            mod = action.split(":", 1)[1]
            self._helper(action, ["load", mod] + (["--persist"] if self._persist else []), self._loaded)
        elif action.startswith("reload:"):
            _, mod, opt = action.split(":", 2)
            self._helper(action, ["load", mod, "--option", opt, "--reload"] + (["--persist"] if self._persist else []),
                         self._loaded)
        elif action in ("grub_add", "grub_remove"):
            self.grubRequested.emit(ts.grub_preview(self.etc, remove=action == "grub_remove"))
        elif action == "taskmgr":
            QProcess.startDetached("taskmgr.exe", [])
        elif action == "pawnio_repair":
            self._repair_pawnio()

    @Slot(bool)
    def applyGrub(self, remove: bool) -> None:
        self._helper("grub_remove" if remove else "grub_add", ["grub-remove" if remove else "grub-add"], self._done)

    @Slot(bool, result=str)
    def grubCommands(self, remove: bool) -> str:
        if remove:
            return f"sudo rm {ts.DROPIN}\nsudo update-grub\n"
        return (f"sudo mkdir -p /etc/default/grub.d\nsudo tee {ts.DROPIN} >/dev/null <<'EOF'\n"
                f"{ts.DROPIN_TEXT}EOF\nsudo update-grub\n")

    def _repair_pawnio(self) -> None:
        exe = os.path.join(os.path.dirname(sys.executable), "pawnio", "PawnIO_setup.exe")
        if not os.path.exists(exe):
            self._fail("The PawnIO installer isn’t in Fankata’s folder. Reinstall Fankata to repair the driver.")
            return
        import ctypes
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, "-install", None, 1)
        if rc <= 32:
            self._fail("The PawnIO installer didn’t start.")

    def _helper(self, action: str, args: list[str], cb) -> None:
        override = os.environ.get("FANKATA_TROUBLESHOOT")      # tests and demos: run without pkexec
        if override:
            argv = [override] + args
        elif os.path.exists(HELPER):
            argv = ["pkexec", HELPER] + args
        else:
            self._fail("This step needs the installed Fankata package.")
            return
        self._set_busy(action)
        p = QProcess(self)
        handled = []

        def finished(code, _status) -> None:
            if handled:
                return
            handled.append(1)
            try:
                out = bytes(p.readAllStandardOutput()).decode(errors="replace")
                err = bytes(p.readAllStandardError()).decode(errors="replace")
            except RuntimeError:
                return
            p.deleteLater()
            self._set_busy("")
            if argv[0] == "pkexec" and code in (126, 127):
                self._fail("Not authorized: the administrator password wasn’t given.")
                return
            r = None
            for ln in reversed(out.strip().splitlines()):
                try:
                    r = json.loads(ln)
                    break
                except ValueError:
                    continue
            if r is None:
                self._fail((err.strip().splitlines() or [f"The helper failed (exit code {code})."])[-1])
                return
            cb(r)

        def failed(error) -> None:
            if handled or error != QProcess.ProcessError.FailedToStart:
                return
            handled.append(1)
            self._set_busy("")
            self._fail(f"Couldn’t run {argv[0]}.")

        p.finished.connect(finished)
        p.errorOccurred.connect(failed)
        p.start(argv[0], argv[1:])

    def _fail(self, msg: str) -> None:
        self._error = msg
        self.backend.toast.emit("error", msg)
        self._rebuild()

    def _scanned(self, r: dict) -> None:
        if r.get("ok"):
            self._scan = r.get("scan") or {}
            self._scan_raw = r.get("raw", "")
            if r.get("kernel_log") is not None:
                self._facts["kernel_log"] = r["kernel_log"]
        else:
            self._scan = {"error": r.get("error") or "The scan failed."}
        self.run()

    def _loaded(self, r: dict) -> None:
        self._load = r
        if r.get("ok"):
            self.backend.rescanHardware()
        if r.get("kernel_log"):
            self._facts["kernel_log"] = (self._facts.get("kernel_log") or []) + r["kernel_log"]
        if not r.get("ok") and r.get("error"):
            self.backend.toast.emit("error", r["error"])
        self.run()

    def _done(self, r: dict) -> None:
        if not r.get("ok"):
            self._fail(r.get("error") or "That didn’t work.")
        elif r.get("restart"):
            self.backend.toast.emit("info", "Done. It takes effect after you restart the PC.")
        self.run()

    # --- report -----------------------------------------------------------------------
    @Slot(str)
    def copyText(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)

    @Slot()
    def copyReport(self) -> None:
        extra = {"sensors-detect": self._scan_raw, "Driver load": self._load}
        self.copyText(ts.report_text(self._result, self._facts, extra))
        self.backend.toast.emit("info", "Report copied. Paste it into an issue or a message.")

    @Slot(result=str)
    def reportText(self) -> str:
        return ts.report_text(self._result, self._facts, {"sensors-detect": self._scan_raw, "Driver load": self._load})
