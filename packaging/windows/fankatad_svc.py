"""PyInstaller entry point: the Fankata service (fankatad.exe)."""
import os
import sys

if getattr(sys, "frozen", False):
    # pythonnet needs to know which python DLL the frozen app runs on
    os.environ.setdefault("PYTHONNET_PYDLL", os.path.join(sys._MEIPASS, f"python{sys.version_info[0]}{sys.version_info[1]}.dll"))

from fankatad.winsvc import main  # noqa: E402

sys.exit(main())
