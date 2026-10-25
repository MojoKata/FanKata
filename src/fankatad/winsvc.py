"""fankatad as a Windows service (pywin32), plus install/uninstall helpers.

    fankatad.exe                 run under the Service Control Manager
    fankatad.exe --console       run in the foreground (debugging)
    fankatad.exe install|remove|start|stop ...   pywin32 service commands

Hardware: LibreHardwareMonitorLib over the PawnIO driver. A developer option,
HKLM\\SOFTWARE\\Fankata\\Simulate = 1, runs against simulated hardware instead
(used to test in a VM, which has no fan controller).
"""

from __future__ import annotations

import ctypes
import logging
import logging.handlers
import os
import sys
import threading
import time

import servicemanager
import win32event
import win32service
import win32serviceutil
import winreg

from fankata_core import __version__, paths

log = logging.getLogger("fankatad")
SERVICE_NAME = "fankatad"


def _setup_logging() -> None:
    os.makedirs(paths.LOG_DIR, exist_ok=True)
    h = logging.handlers.RotatingFileHandler(os.path.join(paths.LOG_DIR, "fankatad.log"),
                                             maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(h)
    if sys.stderr is not None and not hasattr(sys, "_service"):
        root.addHandler(logging.StreamHandler())


def _simulate_requested() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Fankata") as k:
            return int(winreg.QueryValueEx(k, "Simulate")[0]) == 1
    except OSError:
        return False


def _data_dir() -> str:
    """Where bundled files live: PyInstaller's _internal folder when frozen."""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def _clear_stale_run_dir() -> None:
    """original.json/touched.json describe this boot only (requirement 8.1); /run is
    cleared at boot on Linux, so emulate that by boot time."""
    boot = time.time() - ctypes.windll.kernel32.GetTickCount64() / 1000.0
    for name in ("original.json", "touched.json"):
        p = os.path.join(paths.RUN_DIR, name)
        try:
            if os.path.getmtime(p) < boot:
                os.unlink(p)
        except OSError:
            pass


def set_start_type(start_type: int) -> None:
    """Automatic = Fankata is on; manual (demand) = turned off from the app (requirement 4.6)."""
    scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
    try:
        svc = win32service.OpenService(scm, SERVICE_NAME, win32service.SERVICE_CHANGE_CONFIG)
        try:
            win32service.ChangeServiceConfig(svc, win32service.SERVICE_NO_CHANGE, start_type,
                                             win32service.SERVICE_NO_CHANGE, None, None, 0, None, None, None, None)
        finally:
            win32service.CloseServiceHandle(svc)
    finally:
        win32service.CloseServiceHandle(scm)


def make_backend():
    from .backends.hwmon import HwmonBackend
    from .backends.lhm import LhmBackend, NullBackend
    if _simulate_requested():
        from .simulate import Simulator
        sim = Simulator(paths.SIM_ROOT).start()
        time.sleep(0.3)
        b = HwmonBackend(paths.SIM_ROOT)
        b.describe = lambda: "Simulated hardware (developer mode)"
        b._simulator = sim
        return b
    lib = os.path.join(_data_dir(), "lhm")
    try:
        return LhmBackend(lib)
    except Exception as e:  # missing driver, .NET load failure, ...
        log.error("hardware access unavailable: %s", e)
        return NullBackend(f"Hardware access unavailable: {e}. Reinstall Fankata to install the PawnIO driver.")


def run(stop: threading.Event) -> None:
    from .__main__ import serve
    from .controller import Controller
    from .server_win import PipeServer, WinAuthorizer
    _clear_stale_run_dir()
    ctl = Controller(make_backend(), paths.CONFIG_PATH, paths.RUN_DIR)
    server = PipeServer(paths.PIPE_PATH, ctl, WinAuthorizer())
    # Started at all means Fankata is on: start automatically from now on. Turning it off
    # from the app sets manual start and stops; stopping restores every fan (requirement 8.3).
    try:
        set_start_type(win32service.SERVICE_AUTO_START)
    except Exception as e:
        log.warning("can't set the start type: %s", e)

    def service_disable():
        log.info("turned off from the app")
        try:
            set_start_type(win32service.SERVICE_DEMAND_START)
        except Exception as e:
            log.warning("can't set the start type: %s", e)
        threading.Timer(0.3, stop.set).start()     # let the reply reach the app first
    server.service_disable = service_disable

    def diagnose():
        from fankata_core.winfacts import windows_facts
        hw = ctl.hw
        return windows_facts(service={"running": True, "version": __version__}, chips=hw.chips(),
                             backend=hw.describe(), backend_error=hw.describe() if getattr(hw, "unavailable", False) else "",
                             simulated=hasattr(hw, "_simulator"))
    server.diagnose = diagnose
    stop_hook = threading.Thread(target=lambda: (stop.wait(), ctl.wake.set()), daemon=True)
    stop_hook.start()
    serve(ctl, server, stop)


class FankataService(win32serviceutil.ServiceFramework):
    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = "Fankata fan control"
    _svc_description_ = ("Applies Fankata's temperature curves to fans and pumps. "
                         "When stopped, every fan returns to firmware control.")

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = threading.Event()
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING, waitHint=15000)
        self.stop_event.set()

    SvcShutdown = SvcStop

    def SvcDoRun(self):
        sys._service = True
        _setup_logging()
        servicemanager.LogInfoMsg(f"Fankata service {__version__} starting")
        try:
            run(self.stop_event)
        except Exception:
            log.exception("service failed")
            raise
        finally:
            servicemanager.LogInfoMsg("Fankata service stopped; fans returned to firmware control")


def main() -> int:
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(FankataService)
        servicemanager.StartServiceCtrlDispatcher()
        return 0
    if sys.argv[1] == "--console":
        _setup_logging()
        stop = threading.Event()
        try:
            run(stop)
        except KeyboardInterrupt:
            stop.set()
        return 0
    if sys.argv[1] == "--version":
        print(f"fankatad {__version__}")
        return 0
    win32serviceutil.HandleCommandLine(FankataService)
    return 0


if __name__ == "__main__":
    sys.exit(main())
