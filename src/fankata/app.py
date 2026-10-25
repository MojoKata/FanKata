"""Application startup."""

from __future__ import annotations

import argparse
import os
import signal
import sys

from fankata_core import __version__, protocol
from fankata_core.config import DEFAULT_PATH

QML_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qml")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fankata", description="Fankata fan control.")
    ap.add_argument("--socket", default=protocol.SOCKET_PATH)
    ap.add_argument("--sysfs-root", default="/", help="prefix for /sys in read-only mode (tests and demos)")
    ap.add_argument("--config", default=DEFAULT_PATH, help="config file read in read-only mode")
    ap.add_argument("--theme", choices=["system", "dark", "light"], help="override the saved theme for this run")
    ap.add_argument("--tour", metavar="DIR", help="save screenshots of each screen to DIR and exit")
    ap.add_argument("--tour-warmup", type=int, default=0, metavar="N",
                    help="with --tour: first wait until N seconds of probe history exist")
    ap.add_argument("--tour-only", default="", metavar="NAMES",
                    help="with --tour: only these screens (comma-separated), e.g. 12-service-off")
    ap.add_argument("--version", action="version", version=f"fankata {__version__}")
    a, qt_args = ap.parse_known_args(argv)

    if a.tour:
        # Offscreen rendering; on Windows the offscreen platform can't see system
        # fonts, so the normal platform is used (the window is grabbed, not shown).
        if os.name != "nt":
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6 import QtQuick  # noqa: F401  (registers QQuickWindow for rootObjects())

    from .backend import Backend

    if os.name == "nt":      # own taskbar group and icon rather than python's
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Fankata.Fankata")
    app = QGuiApplication([sys.argv[0]] + qt_args)
    app.setApplicationName("Fankata")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("Fankata")
    app.setDesktopFileName("fankata")
    app.setWindowIcon(QIcon(os.path.join(QML_DIR, "assets", "art", "fankata.svg")))
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    backend = Backend(a.socket, a.sysfs_root, a.config)
    from .troubleshooter import Troubleshooter
    troubleshoot = Troubleshooter(backend, a.sysfs_root, os.path.join(a.sysfs_root, "etc") if a.sysfs_root != "/" else "/etc")
    engine = QQmlApplicationEngine()
    ctx = engine.rootContext()
    ctx.setContextProperty("backend", backend)
    ctx.setContextProperty("troubleshoot", troubleshoot)
    ctx.setContextProperty("appVersion", __version__)
    ctx.setContextProperty("themeOverride", a.theme or "")
    ctx.setContextProperty("tourDir", os.path.abspath(a.tour) if a.tour else "")
    ctx.setContextProperty("serviceHint", "Start the “Fankata fan control” service in Services, or reinstall Fankata."
                           if os.name == "nt" else "Start it with:  sudo systemctl start fankata")
    engine.load(QUrl.fromLocalFile(os.path.join(QML_DIR, "Main.qml")))
    if not engine.rootObjects():
        return 1
    if a.tour:
        from .tour import Tour
        tour = Tour(engine.rootObjects()[0], backend, a.tour, warmup=a.tour_warmup, only=a.tour_only)
        tour.start()
    return app.exec()
