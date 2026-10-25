#!/usr/bin/python3 -I
# Fankata service launcher: runs as root with the system python3 in isolated mode.
# Only the standard library plus the vendored tomli (for Python 3.10) are on the path.
import sys

sys.dont_write_bytecode = True
sys.path[:0] = ["/opt/fankata/lib", "/opt/fankata/vendor/core"]

from fankatad.__main__ import main  # noqa: E402

sys.exit(main())
