"""Simulated hwmon sysfs for tests and demos (the implementation lives in fankatad.simulate).

    python3 tests/fakesysfs.py /tmp/fake --simulate
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from fankatad.simulate import CHIPS, Simulator, build, main, simulate  # noqa: E402,F401

if __name__ == "__main__":
    main()
