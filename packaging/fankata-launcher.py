#!/usr/bin/python3 -I
# Fankata GUI launcher. PySide6 is bundled under /opt/fankata; the system python3 runs it.
import sys

sys.dont_write_bytecode = True
sys.path[:0] = ["/opt/fankata/lib", "/opt/fankata/vendor/core", "/opt/fankata/vendor/gui"]
sys.argv[0] = "fankata"

from fankata.app import main  # noqa: E402

sys.exit(main())
