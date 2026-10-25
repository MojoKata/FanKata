"""Packaging pieces: the service on/off helper and the polkit policy (requirement 4.6)."""
import os
import stat
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
HELPER = os.path.join(ROOT, "packaging", "fankata-servicectl")


class ServiceCtlTests(unittest.TestCase):
    def run_helper(self, *args):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "calls")
            fake = os.path.join(d, "systemctl")
            with open(fake, "w") as f:
                f.write(f'#!/bin/sh\necho "$@" >> {log}\n')
            os.chmod(fake, stat.S_IRWXU)
            r = subprocess.run(["sh", HELPER, *args], env={**os.environ, "PATH": d + os.pathsep + os.environ["PATH"]},
                               capture_output=True, text=True)
            calls = open(log).read().split("\n")[:-1] if os.path.exists(log) else []
            return r.returncode, calls

    def test_enable_disable(self):
        self.assertEqual(self.run_helper("enable"), (0, ["enable --now fankata.service"]))
        self.assertEqual(self.run_helper("disable"), (0, ["disable --now fankata.service"]))
        self.assertEqual(self.run_helper("status"), (0, ["is-active fankata.service"]))

    def test_rejects_anything_else(self):
        for args in [(), ("start",), ("enable; reboot",), ("--now",)]:
            code, calls = self.run_helper(*args)
            self.assertEqual(code, 2, args)
            self.assertEqual(calls, [], args)


class PolicyTests(unittest.TestCase):
    def test_actions(self):
        root = ET.parse(os.path.join(ROOT, "packaging", "org.fankata.policy")).getroot()
        actions = {a.get("id"): a for a in root.iter("action")}
        self.assertIn("org.fankata.control", actions)
        svc = actions["org.fankata.service"]
        self.assertEqual(svc.find("defaults/allow_active").text, "yes")
        self.assertEqual(svc.find("defaults/allow_any").text, "auth_admin_keep")
        exec_path = {a.get("key"): a.text for a in svc.iter("annotate")}["org.freedesktop.policykit.exec.path"]
        self.assertEqual(exec_path, "/opt/fankata/bin/fankata-servicectl")

    def test_troubleshoot_needs_a_password(self):
        root = ET.parse(os.path.join(ROOT, "packaging", "org.fankata.policy")).getroot()
        ts = next(a for a in root.iter("action") if a.get("id") == "org.fankata.troubleshoot")
        for k in ("allow_any", "allow_inactive", "allow_active"):
            self.assertEqual(ts.find(f"defaults/{k}").text, "auth_admin_keep", k)
        exec_path = {a.get("key"): a.text for a in ts.iter("annotate")}["org.freedesktop.policykit.exec.path"]
        self.assertEqual(exec_path, "/opt/fankata/bin/fankata-troubleshoot")
        self.assertTrue(os.access(os.path.join(ROOT, "packaging", "fankata-troubleshoot"), os.X_OK))


if __name__ == "__main__":
    unittest.main()
