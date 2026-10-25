"""GUI check: turning the service off and on from the app (requirement 4.6).

    .venv/bin/python tests/gui_service.py      (needs PySide6; runs offscreen)

Uses FANKATA_SERVICECTL to substitute a script that stops/starts a test fankatad
(the installed app uses pkexec + fankata-servicectl, or sc.exe on Windows).
Checks: off → the app goes read-only and every fan is back under firmware control;
on → the app reconnects and the fans are controlled again.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [os.path.join(ROOT, "src"), HERE]
os.environ.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software")

import fakesysfs  # noqa: E402

work = tempfile.mkdtemp(prefix="fankata-svc-")
root = os.path.join(work, "root")
fakesysfs.build(root)
os.makedirs(os.path.join(work, "etc"))
shutil.copy(os.path.join(ROOT, "scripts/demo/config.toml"), os.path.join(work, "etc/config.toml"))
sock = os.path.join(work, "s.sock")
pidfile = os.path.join(work, "svc.pid")
svc_cmd = (f'PYTHONPATH={os.path.join(ROOT, "src")} {sys.executable} -m fankatad --sysfs-root {root} '
           f'--config {work}/etc/config.toml --run-dir {work}/run --socket {sock} --no-auth')
ctl = os.path.join(work, "servicectl")
with open(ctl, "w") as f:
    f.write(f"""#!/bin/sh
case "$1" in
  enable)  {svc_cmd} >/dev/null 2>&1 & echo $! > {pidfile} ;;
  disable) kill -TERM $(cat {pidfile}); while kill -0 $(cat {pidfile}) 2>/dev/null; do sleep 0.1; done ;;
esac
""")
os.chmod(ctl, 0o755)
os.environ["FANKATA_SERVICECTL"] = ctl
subprocess.run([ctl, "enable"], check=True)
time.sleep(1)

from PySide6.QtCore import QCoreApplication  # noqa: E402

from fankata.backend import Backend  # noqa: E402

app = QCoreApplication(sys.argv)
backend = Backend(sock, root, os.path.join(work, "etc/config.toml"))
EN = os.path.join(root, "sys/devices/platform/nct6775.656/hwmon/hwmon3/pwm2_enable")


def pump(seconds, until=None):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)
        if until and until():
            return True
    return until() if until else True


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        raise SystemExit(1)


toasts = []
backend.toast.connect(lambda kind, text: toasts.append((kind, text)))
try:
    pump(5, lambda: backend.connected and any(f["managed"] for f in backend.fans))
    check(backend.connected, "connected to the service")
    pump(2)
    check(open(EN).read().strip() == "1", "CPU Fan under Fankata control (pwm2_enable = 1)")

    backend.setServiceEnabled(False)
    check(backend.serviceBusy, "turning off: busy")
    check(pump(15, lambda: not backend.serviceBusy), "turned off")
    check(not backend.connected and backend.readOnly, "the app is read-only")
    check(open(EN).read().strip() == "5", "CPU Fan back under firmware control (pwm2_enable = 5)")
    check(toasts and toasts[-1][0] == "info" and "off" in toasts[-1][1], f"told the user: {toasts[-1][1]!r}")

    backend.setServiceEnabled(True)
    check(pump(15, lambda: not backend.serviceBusy), "turned on")
    check(backend.connected, "reconnected")
    pump(3)
    check(open(EN).read().strip() == "1", "CPU Fan controlled again")
    print("all service toggle checks passed")
finally:
    subprocess.run([ctl, "disable"])
    shutil.rmtree(work, ignore_errors=True)
