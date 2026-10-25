"""The GUI's probe history: seeded from the service, one point per service sample."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QCoreApplication
    from fankata.backend import Backend
except ImportError:          # PySide6 not installed: skip (the service tests still run)
    Backend = None


def state(seq, cpu, history=None):
    s = {"service": {"readonly": False}, "config": {"curves": [], "probes": [], "fans": {}},
         "fans": [], "probes": [{"name": "sys.cpu", "kind": "system", "desc": "", "value": cpu, "error": None}],
         "pulse": None, "last_pulse": None, "sample": {"seq": seq, "interval": 1.0}}
    if history is not None:
        s["history"] = history
    return s


@unittest.skipIf(Backend is None, "PySide6 not available")
class GuiHistoryTests(unittest.TestCase):
    def setUp(self):
        self.app = QCoreApplication.instance() or QCoreApplication([])
        self.b = Backend("/nonexistent.sock", "/nonexistent", "/nonexistent.toml")
        self.b.ro_timer.stop()

    def hist(self):
        return next(p for p in self.b.probes if p["name"] == "sys.cpu")["history"]

    def test_seed_then_append_per_sample(self):
        self.b._apply(state(7, 50.0, {"sys.cpu": [48.0, 49.0, 50.0]}))
        self.assertEqual(self.hist(), [48.0, 49.0, 50.0])
        self.b._apply(state(7, 50.0))            # same sample again (e.g. a command reply): no new point
        self.assertEqual(self.hist(), [48.0, 49.0, 50.0])
        self.b._apply(state(8, 51.5))
        self.assertEqual(self.hist(), [48.0, 49.0, 50.0, 51.5])

    def test_missing_readings_are_kept_as_gaps(self):
        self.b._apply(state(1, 50.0, {"sys.cpu": [50.0]}))
        self.b._apply(state(2, None))
        self.assertEqual(self.hist(), [50.0, None])


if __name__ == "__main__":
    unittest.main()
