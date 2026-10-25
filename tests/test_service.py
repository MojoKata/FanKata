import json
import os
import socket
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(__file__)
sys.path[:0] = [os.path.join(HERE, "..", "src"), HERE]

import fakesysfs  # noqa: E402
from fankata_core import config as cfgmod, hwmon, protocol  # noqa: E402
from fankatad.controller import Controller, restore_from_files  # noqa: E402
from fankatad.polkit import Authorizer, process_start_time  # noqa: E402
from fankatad.server import Server  # noqa: E402

NCT = "sys/devices/platform/nct6775.656/hwmon/hwmon3"
KRAKEN = "sys/devices/pci0000:00/0000:00:14.0/usb1/1-9/1-9:1.0/0003:1E71:2007.0004/hwmon/hwmon4"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "root")
        self.run = os.path.join(self.tmp.name, "run")
        self.cfgpath = os.path.join(self.tmp.name, "etc", "config.toml")
        fakesysfs.build(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def f(self, rel, name):
        return os.path.join(self.root, rel, name)

    def read(self, rel, name):
        return hwmon.read_int(self.f(rel, name))

    def write(self, rel, name, v):
        hwmon.write_int(self.f(rel, name), v)

    def ctl(self):
        return Controller(self.root, self.cfgpath, self.run)

    def manage(self, ctl, fid="nct6798:pwm2", curve="Quiet", probe="sys.cpu"):
        c = ctl.cfg.copy()
        c.fans[fid] = cfgmod.FanSettings(curve=curve, probe=probe)
        self.assertEqual(ctl.set_config(c.to_dict()), [])


class ControllerTests(Base):
    def test_default_config_created(self):
        self.ctl()
        self.assertTrue(os.path.exists(self.cfgpath))
        with open(self.cfgpath) as f:
            self.assertIn("Balanced", f.read())

    def test_take_control_and_restore_auto(self):
        ctl = self.ctl()
        self.manage(ctl)
        ctl.tick()
        self.assertEqual(self.read(NCT, "pwm2_enable"), 1)
        cpu = ctl.temps["sys.cpu"]
        want = hwmon.duty_to_pwm(__import__("fankata_core.curve", fromlist=["x"]).evaluate(ctl.cfg.curve("Quiet").points, cpu))
        self.assertEqual(self.read(NCT, "pwm2"), want)
        st = {f["id"]: f for f in ctl.state()["fans"]}
        self.assertTrue(st["nct6798:pwm2"]["managed"])
        self.assertEqual(st["nct6798:pwm2"]["restore"], {"mode": "auto", "duty": None})
        # unmanage → original SmartFan mode (5) comes back
        c = ctl.cfg.copy()
        c.fans["nct6798:pwm2"].curve = None
        self.assertEqual(ctl.set_config(c.to_dict()), [])
        ctl.tick()
        self.assertEqual(self.read(NCT, "pwm2_enable"), 5)
        self.assertEqual(ctl.touched, set())

    def test_restore_fixed_when_original_manual(self):
        self.write(NCT, "pwm3_enable", 1)
        self.write(NCT, "pwm3", 100)
        ctl = self.ctl()
        self.manage(ctl, "nct6798:pwm3", "Full blast")
        ctl.tick()
        self.assertEqual(self.read(NCT, "pwm3"), 255)
        self.assertEqual(ctl.restore("nct6798:pwm3")["ok"], True)
        self.assertEqual(self.read(NCT, "pwm3"), 100)
        self.assertEqual(ctl.restore_mode("nct6798:pwm3"), {"mode": "fixed", "duty": 39})

    def test_restore_without_enable_file(self):
        os.unlink(self.f(NCT, "pwm4_enable"))
        before = self.read(NCT, "pwm4")
        ctl = self.ctl()
        self.manage(ctl, "nct6798:pwm4", "Full blast")
        ctl.tick()
        self.assertEqual(self.read(NCT, "pwm4"), 255)
        ctl.restore("nct6798:pwm4")
        self.assertEqual(self.read(NCT, "pwm4"), before)

    def test_restart_does_not_record_manual_as_default(self):
        ctl = self.ctl()
        self.manage(ctl)
        ctl.tick()
        # service crashes and restarts: originals must still say SmartFan (5)
        ctl2 = self.ctl()
        self.assertEqual(ctl2.originals["nct6798:pwm2"]["enable"], 5)
        self.assertIn("nct6798:pwm2", ctl2.controlled)
        ctl2.restore_all()
        self.assertEqual(self.read(NCT, "pwm2_enable"), 5)

    def test_restore_from_files_after_crash(self):
        ctl = self.ctl()
        self.manage(ctl)
        ctl.tick()
        del ctl                        # "killed": no restore ran
        self.assertEqual(restore_from_files(self.root, self.run), 0)
        self.assertEqual(self.read(NCT, "pwm2_enable"), 5)

    def test_probe_failure_runs_full_speed(self):
        ctl = self.ctl()
        c = ctl.cfg.copy()
        c.probes.append(cfgmod.ProbeDef("broken", "sys.cpu / (sys.cpu - sys.cpu)"))
        c.fans["nct6798:pwm2"] = cfgmod.FanSettings(curve="Quiet", probe="broken")
        self.assertEqual(ctl.set_config(c.to_dict()), [])
        ctl.tick()
        self.assertEqual(self.read(NCT, "pwm2"), 255)
        st = {f["id"]: f for f in ctl.state()["fans"]}["nct6798:pwm2"]
        self.assertEqual(st["status"], "warning")

    def test_curve_without_probe_is_not_controlled(self):
        ctl = self.ctl()
        self.manage(ctl, probe=None)
        ctl.tick()
        self.assertEqual(self.read(NCT, "pwm2_enable"), 5)
        st = {f["id"]: f for f in ctl.state()["fans"]}["nct6798:pwm2"]
        self.assertEqual(st["status"], "warning")

    def test_set_config_rejects_invalid(self):
        ctl = self.ctl()
        c = ctl.cfg.copy()
        c.curves[0].points = [[20, 10], [40, 30]]
        self.assertTrue(ctl.set_config(c.to_dict()))
        self.assertNotEqual(cfgmod.load(self.cfgpath).curves[0].points, [[20, 10], [40, 30]])

    def test_pulse(self):
        ctl = self.ctl()
        t0 = 1000.0
        self.assertIsNone(ctl.start_pulse("nct6798:pwm3"))
        ctl.pulse.started = t0
        t = t0
        while ctl.pulse:
            fakesysfs.simulate(self.root, t - t0, dt=0.25)
            ctl.tick(t)
            t += 0.25
        self.assertEqual(ctl.last_pulse["kind"], "self")
        self.assertIn("fan3 is following the pulse", ctl.last_pulse["message"])
        self.assertEqual(self.read(NCT, "pwm3_enable"), 5)       # unmanaged → default again

    def test_pulse_no_tach(self):
        ctl = self.ctl()
        ctl.start_pulse("nct6798:pwm6")
        ctl.pulse.started = 0.0
        t = 0.0
        while ctl.pulse:
            fakesysfs.simulate(self.root, t, dt=0.25)
            ctl.tick(t)
            t += 0.25
        self.assertEqual(ctl.last_pulse["kind"], "none")

    def test_pulse_pump_never_slows(self):
        ctl = self.ctl()
        current = hwmon.pwm_to_duty(self.read(KRAKEN, "pwm1"))
        ctl.start_pulse("nzxt-kraken3:pwm1")
        self.assertEqual(ctl.pulse.low, current)
        ctl.stop_pulse()
        ctl.tick()
        self.assertIsNone(ctl.pulse)
        self.assertEqual(ctl.last_pulse["stopped"], "Stopped.")


class HistoryTests(Base):
    def test_one_sample_per_second_even_during_pulse(self):
        ctl = self.ctl()
        c = ctl.cfg.copy()
        c.probes.append(cfgmod.ProbeDef("loop", "(sys.coolant - 25) * 2 + 25"))
        self.assertEqual(ctl.set_config(c.to_dict()), [])
        t = 100.0
        for _ in range(12):              # 3 s of 0.25 s ticks, as during a Speed pulse
            ctl.tick(t)
            t += 0.25
        self.assertEqual(ctl.sample_seq, 3)
        self.assertEqual(len(ctl.history["sys.cpu"]), 3)
        self.assertEqual(len(ctl.history["loop"]), 3)          # custom probes too
        self.assertAlmostEqual(ctl.history["sys.cpu"][-1], round(ctl.temps["sys.cpu"], 2))

    def test_history_only_in_initial_state(self):
        ctl = self.ctl()
        ctl.tick(0.0)
        self.assertNotIn("history", ctl.state())
        full = ctl.state(include_history=True)
        self.assertEqual(len(full["history"]["sys.cpu"]), 1)
        self.assertEqual(full["sample"], {"seq": 1, "interval": 1.0})

    def test_history_is_capped(self):
        from fankatad.controller import HISTORY_LEN
        ctl = self.ctl()
        for i in range(HISTORY_LEN + 10):
            ctl.tick(float(i))
        self.assertEqual(len(ctl.history["sys.cpu"]), HISTORY_LEN)


class ServerTests(Base):
    def setUp(self):
        super().setUp()
        self.controller = self.ctl()
        self.sock = os.path.join(self.tmp.name, "s.sock")

    def talk(self, server, *msgs):
        server.start()
        try:
            c = socket.socket(socket.AF_UNIX)
            c.connect(self.sock)
            f = c.makefile("rwb")
            out = []
            for m in msgs:
                f.write(protocol.encode(m))
                f.flush()
                out.append(json.loads(f.readline()))
            c.close()
            return out
        finally:
            server.close()

    def test_protocol(self):
        s = Server(self.sock, self.controller, Authorizer(enabled=False))
        cfg = self.controller.cfg.copy()
        cfg.fans["nct6798:pwm2"] = cfgmod.FanSettings(name="CPU Fan")
        hello, state, ok, bad = self.talk(
            s, {"id": 1, "cmd": "hello", "version": protocol.VERSION}, {"id": 2, "cmd": "get_state"},
            {"id": 3, "cmd": "set_config", "config": cfg.to_dict()},
            {"id": 4, "cmd": "nope"})
        self.assertTrue(hello["result"]["compatible"])
        self.assertEqual(len(state["result"]["fans"]), 6)
        self.assertIn("history", state["result"])                     # sent on request/subscribe
        self.assertTrue(ok["ok"])
        self.assertEqual({f["id"]: f for f in ok["result"]["fans"]}["nct6798:pwm2"]["name"], "CPU Fan")
        self.assertFalse(bad["ok"])

    def test_writes_need_authorization(self):
        class Deny(Authorizer):
            def check(self, pid, uid):
                return False, "Not authorized to change fan control."
        s = Server(self.sock, self.controller, Deny())
        r, = self.talk(s, {"id": 1, "cmd": "pulse_start", "fan": "nct6798:pwm2"})
        self.assertFalse(r["ok"])
        self.assertIn("Not authorized", r["error"])

    def test_service_disable(self):
        calls = []
        s = Server(self.sock, self.controller, Authorizer(enabled=False))
        s.service_disable = lambda: calls.append(1)            # what the Windows service installs
        r, = self.talk(s, {"id": 1, "cmd": "service_disable"})
        self.assertTrue(r["ok"])
        self.assertEqual(calls, [1])
        s2 = Server(self.sock, self.controller, Authorizer(enabled=False))   # Linux: no hook
        r, = self.talk(s2, {"id": 1, "cmd": "service_disable"})
        self.assertFalse(r["ok"])

    def test_service_disable_needs_authorization(self):
        class Deny(Authorizer):
            def check(self, pid, uid):
                return False, "Not authorized to change fan control."
        calls = []
        s = Server(self.sock, self.controller, Deny())
        s.service_disable = lambda: calls.append(1)
        r, = self.talk(s, {"id": 1, "cmd": "service_disable"})
        self.assertFalse(r["ok"])
        self.assertEqual(calls, [])

    def test_start_time(self):
        self.assertIsInstance(process_start_time(os.getpid()), int)


if __name__ == "__main__":
    unittest.main()
