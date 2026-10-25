"""GUI check: real mouse drags on the Fans view against a live fankatad + fake sysfs.

    .venv/bin/python tests/gui_drag.py        (needs PySide6 with QtTest; runs offscreen)

Checks: reorder within a group, moving a fan to another Probe group, an unmanaged
fan taking the nearest fan's Curve, and dropping into "Unmanaged fans".
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
os.environ.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QT_QUICK_CONTROLS_STYLE="Basic")

import fakesysfs  # noqa: E402

work = tempfile.mkdtemp(prefix="fankata-drag-")
os.environ["XDG_CONFIG_HOME"] = os.path.join(work, "xdg")
fakesysfs.build(os.path.join(work, "root"))
os.makedirs(os.path.join(work, "etc"))
shutil.copy(os.path.join(ROOT, "scripts/demo/config.toml"), os.path.join(work, "etc/config.toml"))
sock = os.path.join(work, "s.sock")
svc = subprocess.Popen([sys.executable, "-m", "fankatad", "--sysfs-root", os.path.join(work, "root"),
                        "--config", os.path.join(work, "etc/config.toml"), "--run-dir", os.path.join(work, "run"),
                        "--socket", sock, "--no-auth"], env={**os.environ, "PYTHONPATH": os.path.join(ROOT, "src")},
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)

from PySide6 import QtQuick  # noqa: E402,F401
from PySide6.QtCore import QPoint, QPointF, QUrl, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from fankata.app import QML_DIR  # noqa: E402
from fankata.backend import Backend  # noqa: E402

app = QGuiApplication(sys.argv)
backend = Backend(sock, os.path.join(work, "root"), os.path.join(work, "etc/config.toml"))
engine = QQmlApplicationEngine()
for k, v in {"backend": backend, "appVersion": "test", "themeOverride": "dark", "tourDir": "", "serviceHint": ""}.items():
    engine.rootContext().setContextProperty(k, v)
engine.load(QUrl.fromLocalFile(os.path.join(QML_DIR, "Main.qml")))
win = engine.rootObjects()[0]
from PySide6.QtQuick import QQuickItem  # noqa: E402
fans_view = win.findChild(QQuickItem, "fansView") or win.contentItem().findChild(QQuickItem, "fansView")


def pump(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def layout():
    v = fans_view.property("layout")
    return v.toVariant() if hasattr(v, "toVariant") else v


def to_window(x, y):
    content = fans_view.findChild(QQuickItem, "fanContent")
    p = content.mapToScene(QPointF(x, y))
    return QPoint(int(p.x()), int(p.y()))


def call(name, *args):
    """Window-coordinate points: tilePoint(fan name, fx, fy) or slotPoint(group key, index, fx, fy)."""
    L = layout()
    cw, ch = fans_view.property("cardW"), fans_view.property("cardH")
    gap, cols = fans_view.property("gap"), fans_view.property("cols")
    if name == "tilePoint":
        fname, fx, fy = args
        fid = next(f["id"] for f in backend.fans if f["name"] == fname)
        p = L["pos"][fid]
        return to_window(p["x"] + cw * fx, p["y"] + ch * fy)
    key, index, fx, fy = args
    h = L["heads"][key]
    return to_window((index % cols) * (cw + gap) + cw * fx, h["tilesTop"] + (index // cols) * (ch + gap) + ch * fy)


def drag(a: QPoint, b: QPoint, steps=24):
    QTest.mouseMove(win, a)
    QTest.mousePress(win, Qt.LeftButton, Qt.NoModifier, a)
    for i in range(1, steps + 1):
        QTest.mouseMove(win, QPoint(a.x() + (b.x() - a.x()) * i // steps, a.y() + (b.y() - a.y()) * i // steps))
        pump(0.02)
    QTest.mouseRelease(win, Qt.LeftButton, Qt.NoModifier, b)
    pump(1.5)


def fan(name):
    return next(f for f in backend.fans if f["name"] == name)


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        raise SystemExit(1)


try:
    for _ in range(50):
        pump(0.1)
        if backend.connected and backend.fans:
            break
    win.resize(1280, 1600)          # tall window: every group visible, no scrolling needed
    pump(1)

    # 1. reorder within sys.cpu: Rear Exhaust before CPU Fan
    drag(call("tilePoint", "Rear Exhaust", 0.5, 0.2), call("slotPoint", "sys.cpu", 0, 0.3, 0.3))
    ids = {f["name"]: f["id"] for f in backend.fans}
    fo = backend.prefs["fanOrder"]
    check(fo.index(ids["Rear Exhaust"]) < fo.index(ids["CPU Fan"]), "reorder within a group saves the order")
    check(fan("Rear Exhaust")["probe"] == "sys.cpu", "reorder keeps the probe")

    # 2. managed fan to another group: CPU Fan → loop keeps its curve
    drag(call("tilePoint", "CPU Fan", 0.5, 0.2), call("slotPoint", "loop", 2, 0.5, 0.4))
    pump(1.5)
    check(fan("CPU Fan")["probe"] == "loop" and fan("CPU Fan")["curve"] == "Quiet", "drop into loop sets the probe, keeps the curve")

    # 3. unmanaged fan into loop next to Radiator Fan takes its curve (Balanced)
    rad = call("tilePoint", "Radiator Fan", 0.6, 0.6)
    drag(call("tilePoint", "Front Intake", 0.5, 0.2), QPoint(rad.x() + 40, rad.y() + 20))
    pump(1.5)
    fi = fan("Front Intake")
    check(fi["probe"] == "loop" and fi["curve"] == "Balanced", f"unmanaged fan took the nearest curve ({fi['curve']})")
    check(fi["managed"], "service confirms it is managed")

    # 4. managed fan into Unmanaged fans → system default
    drag(call("tilePoint", "Rear Exhaust", 0.5, 0.2), call("slotPoint", "", 1, 0.5, 0.4))
    pump(1.5)
    check(not fan("Rear Exhaust")["curve"] and not fan("Rear Exhaust")["managed"], "drop into Unmanaged returns it to system default")

    # 5. a plain click still selects
    p = call("tilePoint", "AIO Pump", 0.5, 0.2)
    QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, p)
    pump(0.5)
    check(fans_view.property("selected") == ids["AIO Pump"], "click selects the fan")
    print("all drag checks passed")
finally:
    del engine
    svc.terminate()
    svc.wait()
    shutil.rmtree(work, ignore_errors=True)
