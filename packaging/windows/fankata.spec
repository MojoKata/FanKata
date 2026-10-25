# PyInstaller spec: one folder holding fankata.exe (GUI) and fankatad.exe (service).
# Built under Wine by scripts/build-windows.sh.
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
SRC = os.path.join(ROOT, "src")
LHM = os.path.join(ROOT, "build", "windows-deps", "lhm")
ICON = os.path.join(SPECPATH, "fankata.ico")

gui = Analysis([os.path.join(SPECPATH, "fankata_gui.py")], pathex=[SRC],
               datas=[(os.path.join(SRC, "fankata", "qml"), "fankata/qml"),
                      (os.path.join(SRC, "fankata", "tips"), "fankata/tips")],
               hiddenimports=["fankata.tour", "fankata.troubleshooter", "fankata_core.winfacts"],
               excludes=["tkinter", "unittest", "pydoc", "fankatad", "pythonnet", "clr_loader"])
svc = Analysis([os.path.join(SPECPATH, "fankatad_svc.py")], pathex=[SRC],
               datas=[(LHM, "lhm")],
               hiddenimports=["win32timezone", "fankata_core.winfacts", "fankatad.backends.lhm", "fankatad.backends.hwmon",
                              "fankatad.simulate", "fankatad.server_win", "pythonnet", "clr_loader"],
               excludes=["tkinter", "PySide6", "shiboken6", "fankata"])

gui_exe = EXE(PYZ(gui.pure), gui.scripts, [], exclude_binaries=True, name="fankata",
              console=False, icon=ICON, version=None)
svc_exe = EXE(PYZ(svc.pure), svc.scripts, [], exclude_binaries=True, name="fankatad",
              console=True, icon=ICON)
COLLECT(gui_exe, gui.binaries, gui.datas, svc_exe, svc.binaries, svc.datas, name="Fankata")
