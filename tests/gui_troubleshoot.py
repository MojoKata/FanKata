"""GUI check: Troubleshoot fans end to end (requirement 4.7), offscreen.

    .venv/bin/python tests/gui_troubleshoot.py [--shots DIR]

A PC with no fan control: the Fans view offers Troubleshoot; the dialog scans
(sensors-detect, faked), loads the driver the scan names, and the fans appear.
Then the firmware-conflict path: the driver loads but can't claim its chip, the
dialog offers the boot option, the confirmation shows the file before and after,
and writing it leaves "Restart to use the boot option". FANKATA_TROUBLESHOOT
stands in for pkexec + fankata-troubleshoot.
"""
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [os.path.join(ROOT, "src"), HERE]
os.environ.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QT_QUICK_CONTROLS_STYLE="Basic")
SHOTS = sys.argv[sys.argv.index("--shots") + 1] if "--shots" in sys.argv else ""

import fakesysfs  # noqa: E402
from test_troubleshoot import SD_NCT  # noqa: E402

work = tempfile.mkdtemp(prefix="fankata-ts-")
os.environ["XDG_CONFIG_HOME"] = os.path.join(work, "xdg")
root = os.path.join(work, "root")


def make_etc():      # fakesysfs.build() replaces the whole tree
    os.makedirs(os.path.join(root, "etc", "default", "grub.d"), exist_ok=True)
    with open(os.path.join(root, "etc", "default", "grub"), "w") as f:
        f.write('GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"\nGRUB_CMDLINE_LINUX=""\n')
    os.makedirs(os.path.join(root, "proc"), exist_ok=True)
    with open(os.path.join(root, "proc", "cmdline"), "w") as f:
        f.write("BOOT_IMAGE=/vmlinuz quiet splash\n")


make_etc()
bin_dir = os.path.join(work, "bin")
os.makedirs(bin_dir)
for tool in ("update-grub", "sensors-detect", "apt-get"):
    with open(os.path.join(bin_dir, tool), "w") as f:
        f.write("#!/bin/sh\nexit 0\n")
    os.chmod(os.path.join(bin_dir, tool), 0o755)
os.environ["PATH"] = bin_dir + os.pathsep + os.environ["PATH"]

mode = os.path.join(work, "mode")
log = os.path.join(work, "helper.log")
helper = os.path.join(work, "helper")
CONFLICT = ["nct6775: Found NCT6798D or compatible chip at 0x2e:0x290",
            "ACPI Warning: SystemIO range 0x0000000000000295-0x0000000000000296 conflicts with OpRegion",
            "ACPI: OSL: Resource conflict; ACPI support missing from driver?"]
with open(helper, "w") as f:
    f.write(f"""#!{sys.executable}
import json, os, sys
sys.path[:0] = [{os.path.join(ROOT, "src")!r}, {HERE!r}]
args = sys.argv[1:]
open({log!r}, "a").write(" ".join(args) + "\\n")
mode = open({mode!r}).read().strip() if os.path.exists({mode!r}) else "ok"
if args[0] == "scan":
    from fankata_core.troubleshoot import parse_sensors_detect
    print(json.dumps({{"ok": True, "scan": parse_sensors_detect({SD_NCT!r}), "kernel_log": [], "raw": "..."}}))
elif args[0] == "load":
    if mode == "ok":
        import fakesysfs; fakesysfs.build({root!r})
        print(json.dumps({{"ok": True, "module": args[1], "persist": "--persist" in args, "kernel_log": ["nct6775: Found NCT6798D"]}}))
    else:
        print(json.dumps({{"ok": True, "module": args[1], "persist": "--persist" in args, "kernel_log": {CONFLICT!r}}}))
elif args[0] == "grub-add":
    p = os.path.join({root!r}, "etc/default/grub.d/fankata.cfg")
    from fankata_core.troubleshoot import DROPIN_TEXT
    open(p, "w").write(DROPIN_TEXT)
    print(json.dumps({{"ok": True, "restart": True}}))
""")
os.chmod(helper, 0o755)
os.environ["FANKATA_TROUBLESHOOT"] = helper

from PySide6 import QtQuick  # noqa: E402,F401
from PySide6.QtCore import Q_ARG, QMetaObject, QPoint, QUrl, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from fankata_core import troubleshoot as ts  # noqa: E402
from fankata.app import QML_DIR  # noqa: E402
from fankata.backend import Backend  # noqa: E402
from fankata.troubleshooter import Troubleshooter  # noqa: E402

# this machine's own modules and journal must not leak into the test
ts.module_info = lambda name: {"available": True, "params": ["force_id"]} if name == "nct6775" else {"available": False}
ts.kernel_log = lambda: []

app = QGuiApplication(sys.argv)
backend = Backend(os.path.join(work, "none.sock"), root, os.path.join(work, "config.toml"))
trouble = Troubleshooter(backend, root, os.path.join(root, "etc"))
engine = QQmlApplicationEngine()
ctx = engine.rootContext()
for k, v in {"backend": backend, "troubleshoot": trouble, "appVersion": "test", "themeOverride": "dark", "tourDir": "",
             "serviceHint": ""}.items():
    ctx.setContextProperty(k, v)
engine.load(QUrl.fromLocalFile(os.path.join(QML_DIR, "Main.qml")))
win = engine.rootObjects()[0]
failures = []


def pump(seconds, until=None):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)
        if until and until():
            return True
    return bool(until and until())


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what, flush=True)
    if not cond:
        failures.append(what)


def ids():
    return {c["id"]: c for c in trouble.result.get("checks", [])}


def shot(name):
    if SHOTS:
        pump(0.6)
        os.makedirs(SHOTS, exist_ok=True)
        win.grabWindow().save(os.path.join(SHOTS, name + ".png"))


def item(name):
    return win.findChild(QtQuick.QQuickItem, name)


pump(2.5)
card = item("emptyCard")
check(card is not None and card.isVisible(), "no fans: the Fans view shows the empty card")
shot("16-fans-empty")
btn = item("troubleshootButton")
c = btn.mapToScene(btn.boundingRect().center())
QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, QPoint(int(c.x()), int(c.y())))
check(pump(10, lambda: "scan" in ids()), "Troubleshoot opens the dialog and runs the checks")
check(ids().get("chips", {}).get("st") == "warn", "it reports no sensor chip with fan control")
check(ids()["scan"]["action"]["id"] == "scan" and not ids()["scan"]["action"].get("disabled"), "the scan is offered")
shot("17-troubleshoot")

trouble.act("scan")
check(pump(10, lambda: "load:nct6775" in ids()), "the scan finds the NCT6798D and offers to load nct6775")
check(ids()["chip:Nuvoton NCT6798D"]["st"] == "ok", "the chip row is ok")
shot("18-troubleshoot-found")
trouble.act("load:nct6775")
check(pump(10, lambda: ids().get("load:nct6775", {}).get("st") == "ok"), "loading the driver succeeds")
check(pump(5, lambda: len(backend.fans) > 0), f"the fans appear in the Fans view ({len(backend.fans)})")
check("load nct6775 --persist" in open(log).read(), "the load was asked to persist across boots")
check(not item("emptyCard").isVisible(), "the empty card is gone")

# --- the firmware won't share the chip ---------------------------------------------
shutil.rmtree(os.path.join(root, "sys"))
make_etc()
backend.rescanHardware()
open(mode, "w").write("conflict")
trouble._load = None
trouble._facts["kernel_log"] = []
trouble.run()
pump(3, lambda: not backend.fans)
trouble.act("load:nct6775")
check(pump(10, lambda: "conflict" in ids()), "a resource conflict is reported after the load")
check(ids()["conflict"].get("action", {}).get("id") == "grub_add", "nct6775 has no override option, so the boot option is offered")
win.setProperty("width", 1280)
trouble.act("grub_add")
pump(1)
shot("23-troubleshoot-grub-confirm")
prev = ts.grub_preview(os.path.join(root, "etc"))
check(prev["before"] is None and prev["cmd_after"].endswith(ts.LAX), "the confirmation shows the new file and the added option")
trouble.applyGrub(False)
check(pump(10, lambda: ids().get("grub", {}).get("title") == "Restart to use the boot option"), "after writing: restart to use it")
check(os.path.exists(os.path.join(root, "etc/default/grub.d/fankata.cfg")), "the drop-in file was written")
check(ids()["grub"]["action"]["id"] == "grub_remove", "and it can be removed again")
txt = trouble.reportText()
check("Restart to use the boot option" in txt and "Resource conflict" in txt, "Copy report has the checks and the kernel messages")
QMetaObject.invokeMethod(win, "tour", Q_ARG("QVariant", {"troubleshoot": True, "tipsOpen": True}))
shot("19-troubleshoot-tips")

del engine          # before the context objects it refers to
app.quit()
shutil.rmtree(work, ignore_errors=True)
print("FAILED: " + "; ".join(failures) if failures else "all troubleshoot checks passed")
sys.exit(1 if failures else 0)
