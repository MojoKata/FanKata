import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fankata_core import troubleshoot as ts  # noqa: E402
from fankatad import tshelper  # noqa: E402

# Output shapes from lm-sensors 3.6.0's sensors-detect (Ubuntu 22.04)
SD_NCT = """# sensors-detect version 3.6.0
# Board: ASUSTeK COMPUTER INC. PRIME B550-PLUS
Some Super I/O chips contain embedded sensors. We have to write to
standard I/O ports to probe them. This is usually safe.
Do you want to scan for Super I/O sensors? (YES/no):
Probing for Super-I/O at 0x2e/0x2f
Trying family `National Semiconductor/ITE'...               No
Trying family `SMSC'...                                     No
Trying family `VIA/Winbond/Nuvoton/Fintek'...               Yes
Found `Nuvoton NCT6798D Super IO Sensors'                   Success!
    (address 0x290, driver `nct6775')
Probing for Super-I/O at 0x4e/0x4f

Now follows a summary of the probes I have just done.
Just press ENTER to continue:
Driver `nct6775':
  * ISA bus, address 0x290
    Chip `Nuvoton NCT6798D Super IO Sensors' (confidence: 9)

Driver `k10temp' (autoloaded):
  * Chip `AMD Family 17h thermal sensors' (confidence: 9)

To load everything that is needed, add this to /etc/modules:
#----cut here----
# Chip drivers
nct6775
#----cut here----
Do you want to add these lines automatically to /etc/modules? (yes/NO)
"""
SD_GIGABYTE = """# sensors-detect version 3.6.0
Probing for Super-I/O at 0x2e/0x2f
Trying family `National Semiconductor/ITE'...               Yes
Found unknown chip with ID 0x8688
Probing for Super-I/O at 0x4e/0x4f
Trying family `National Semiconductor/ITE'...               Yes
Found `ITE IT8792E Super IO Sensors'                        Success!
    (address 0xa60, driver `it87')

Now follows a summary of the probes I have just done.
Just press ENTER to continue:
Driver `it87':
  * ISA bus, address 0xa60
    Chip `ITE IT8792E Super IO Sensors' (confidence: 9)

"""

EMPTY = {"platform": "linux", "service": {"running": True, "version": "0.1.0"},
         "chips": [{"key": "k10temp", "name": "k10temp", "pwms": [], "fans": [], "temps": 2, "speed_only": []},
                   {"key": "asus_wmi_sensors", "name": "asus_wmi_sensors", "pwms": [], "fans": [1, 2, 3], "temps": 4,
                    "speed_only": [1, 2, 3]}],
         "board": {"vendor": "ASUSTeK COMPUTER INC.", "name": "PRIME B550-PLUS"}, "kernel": "5.15.0-91-generic",
         "os": "Ubuntu 22.04.4 LTS", "os_id": "ubuntu", "os_version": "22.04", "modules": ["k10temp", "asus_wmi_sensors"],
         "lm_sensors": True, "apt": True, "secure_boot": False, "nvidia": False, "thinkpad_fan_control": None,
         "proc_cmdline": "BOOT_IMAGE=/vmlinuz quiet splash", "grub": {"available": True, "dropin": False},
         "module_info": {"nct6775": {"available": True, "params": ["force_id"]},
                         "it87": {"available": True, "params": ["force_id", "ignore_resource_conflict"]}},
         "kernel_log": []}


def ids(result):
    return {c["id"]: c for c in result["checks"]}


class SensorsDetectTests(unittest.TestCase):
    def test_summary(self):
        r = ts.parse_sensors_detect(SD_NCT)
        nct = [c for c in r["chips"] if c["superio"]]
        self.assertEqual(len(nct), 1)
        self.assertEqual(nct[0]["driver"], "nct6775")
        self.assertEqual(nct[0]["chip"], "Nuvoton NCT6798D")
        self.assertEqual(nct[0]["address"], "0x290")
        self.assertTrue(any(c["driver"] == "k10temp" and c["autoloaded"] for c in r["chips"]))

    def test_unknown_ite(self):
        r = ts.parse_sensors_detect(SD_GIGABYTE)
        self.assertEqual(r["unknown"], [{"id": "0x8688", "family": "National Semiconductor/ITE", "name": "ITE IT8688E"}])
        self.assertEqual([c["chip"] for c in r["chips"]], ["ITE IT8792E"])

    def test_answers_only_allow_the_safe_scans(self):
        answers = ts.SENSORS_DETECT_INPUT.splitlines()
        self.assertEqual(answers[:2], ["y", "y"])          # embedded sensors, Super I/O
        self.assertTrue(all(a == "n" for a in answers[2:]))  # IPMI, ISA, SMBus, writing config


class LinuxCheckTests(unittest.TestCase):
    def test_before_scan(self):
        r = ts.linux_checks(EMPTY)
        c = ids(r)
        self.assertEqual(c["chips"]["st"], "warn")
        self.assertIn("reads sensors only", c["chips"]["detail"])
        self.assertEqual(c["scan"]["tag"], "Optional")
        self.assertTrue(c["scan"]["action"]["lock"])
        self.assertIn("speed_only", c)
        self.assertIn("hwe", c)                 # Ubuntu 22.04 on 5.15 without fan control
        self.assertFalse(r["tips_open"])
        self.assertEqual(r["summary"][0][0], "0 fan controls")

    def test_lm_sensors_missing(self):
        r = ts.linux_checks({**EMPTY, "lm_sensors": False})
        c = ids(r)
        self.assertEqual(c["lm_sensors"]["action"]["id"], "install_lm_sensors")
        self.assertTrue(c["scan"]["action"]["disabled"])

    def test_scan_finds_unloaded_driver(self):
        r = ts.linux_checks(EMPTY, scan=ts.parse_sensors_detect(SD_NCT))
        c = ids(r)
        self.assertEqual(c["chip:Nuvoton NCT6798D"]["st"], "ok")
        load = c["load:nct6775"]
        self.assertEqual(load["action"]["id"], "load:nct6775")
        self.assertIn(ts.MODULES_LOAD, load["check"]["label"])

    def test_conflict_without_module_option_offers_grub(self):
        f = {**EMPTY, "modules": EMPTY["modules"] + ["nct6775"],
             "kernel_log": ["[    3.1] nct6775: Found NCT6798D or compatible chip at 0x2e:0x290",
                            "[    3.1] ACPI Warning: SystemIO range 0x0295-0x0296 conflicts with OpRegion",
                            "[    3.1] ACPI: OSL: Resource conflict; ACPI support missing from driver?"]}
        c = ids(ts.linux_checks(f, scan=ts.parse_sensors_detect(SD_NCT)))
        self.assertEqual(c["conflict"]["st"], "fail")
        self.assertEqual(c["conflict"]["action"]["id"], "grub_add")

    def test_conflict_with_it87_reloads_instead_of_grub(self):
        f = {**EMPTY, "modules": EMPTY["modules"] + ["it87"],
             "kernel_log": ["it87: Found IT8792E chip at 0xa60, revision 3",
                            "it87: ACPI resource conflict, use ignore_resource_conflict=1 to ignore"]}
        c = ids(ts.linux_checks(f))
        self.assertEqual(c["reload:it87"]["action"]["id"], "reload:it87:ignore_resource_conflict=1")
        self.assertIn(ts.MODPROBE_D, c["reload:it87"]["check"]["label"])
        self.assertNotIn("grub_add", json.dumps(c["conflict"]))

    def test_gigabyte(self):
        f = {**EMPTY, "board": {"vendor": "Gigabyte Technology Co., Ltd.", "name": "B550 AORUS ELITE V2"},
             "secure_boot": True, "chips": [EMPTY["chips"][0]],
             "module_info": {"it87": {"available": True, "params": ["force_id"]}}}
        r = ts.linux_checks(f, scan=ts.parse_sensors_detect(SD_GIGABYTE))
        c = ids(r)
        self.assertEqual(c["chip:0x8688"]["st"], "fail")
        self.assertEqual(c["chip:0x8688"]["code"], ts.COMMUNITY_IT87_STEPS)
        self.assertIn("gigabyte", c)
        self.assertIn("secure_boot", c)
        self.assertEqual(r["summary"][2][0], "B550 AORUS ELITE V2")
        self.assertIn("Gigabyte", r["summary"][2][1])

    def test_nothing_to_fix_opens_tips(self):
        scan = {"chips": [], "unknown": [], "no_driver": [], "nothing": True}
        f = {**EMPTY, "os_version": "24.04", "chips": [EMPTY["chips"][0]]}
        r = ts.linux_checks(f, scan=scan)
        self.assertTrue(r["tips_open"])
        self.assertEqual(r["tips_note"], "nothing more could be fixed automatically")

    def test_all_good(self):
        f = {**EMPTY, "chips": [{"key": "nct6798", "name": "nct6798", "pwms": [2, 3], "fans": [2, 3], "temps": 3, "speed_only": []}]}
        r = ts.linux_checks(f)
        c = ids(r)
        self.assertEqual(c["chips"]["st"], "ok")
        self.assertNotIn("hwe", c)
        self.assertFalse(c["scan"]["action"]["primary"])

    def test_dropin_restart_and_remove(self):
        f = {**EMPTY, "grub": {"available": True, "dropin": True}}
        c = ids(ts.linux_checks(f))
        self.assertEqual(c["grub"]["title"], "Restart to use the boot option")
        self.assertEqual(c["grub"]["action"]["id"], "grub_remove")
        f["proc_cmdline"] += " " + ts.LAX
        self.assertEqual(ids(ts.linux_checks(f))["grub"]["st"], "ok")


class GrubTests(unittest.TestCase):
    def test_preview(self):
        with tempfile.TemporaryDirectory() as etc:
            os.makedirs(os.path.join(etc, "default", "grub.d"))
            with open(os.path.join(etc, "default", "grub"), "w") as f:
                f.write('GRUB_DEFAULT=0\nGRUB_CMDLINE_LINUX_DEFAULT="quiet splash"\nGRUB_CMDLINE_LINUX=""\n')
            p = ts.grub_preview(etc)
            self.assertIsNone(p["before"])
            self.assertEqual(p["cmd_before"], "quiet splash")
            self.assertEqual(p["cmd_after"], "quiet splash " + ts.LAX)
            with open(os.path.join(etc, "default", "grub.d", "fankata.cfg"), "w") as f:
                f.write(ts.DROPIN_TEXT)
            self.assertIn(ts.LAX, ts.grub_cmdline(etc)["GRUB_CMDLINE_LINUX_DEFAULT"])
            r = ts.grub_preview(etc, remove=True)
            self.assertEqual(r["cmd_after"], "quiet splash")
            self.assertEqual(r["before"], ts.DROPIN_TEXT.strip().splitlines())


class FakeRun:
    def __init__(self, results=None):
        self.calls, self.results = [], results or {}

    def __call__(self, argv, input=None, timeout=60, env=None):
        self.calls.append(argv)
        for key, res in self.results.items():
            if " ".join(argv).startswith(key):
                return res
        return 0, "", ""


class HelperTests(unittest.TestCase):
    def test_scan(self):
        run = FakeRun({"sensors-detect": (0, SD_NCT, ""), "dmesg": (0, "nct6775: Found NCT6798D\n", "")})
        r = tshelper.Helper("/", run).scan()
        self.assertTrue(r["ok"])
        self.assertEqual(r["scan"]["chips"][0]["driver"], "nct6775")
        self.assertEqual(r["kernel_log"], ["nct6775: Found NCT6798D"])

    def test_load_persist(self):
        with tempfile.TemporaryDirectory() as root:
            run = FakeRun({"modinfo": (0, "/lib/modules/5.15.0/kernel/drivers/hwmon/it87.ko\n", "")})
            h = tshelper.Helper(root, run)
            r = h.load("it87", ["ignore_resource_conflict=1"], persist=True, reload=True)
            self.assertTrue(r["ok"], r)
            self.assertIn(["modprobe", "-r", "it87"], run.calls)
            self.assertIn(["modprobe", "it87", "ignore_resource_conflict=1"], run.calls)
            self.assertIn(["systemctl", "try-restart", "fankata.service"], run.calls)
            with open(os.path.join(root, ts.MODULES_LOAD.lstrip("/"))) as f:
                self.assertEqual(f.read().splitlines()[-1], "it87")
            with open(os.path.join(root, ts.MODPROBE_D.lstrip("/"))) as f:
                self.assertEqual(f.read().splitlines()[-1], "options it87 ignore_resource_conflict=1")
            h.load("it87", ["ignore_resource_conflict=1"], persist=True, reload=False)     # idempotent
            with open(os.path.join(root, ts.MODULES_LOAD.lstrip("/"))) as f:
                self.assertEqual(f.read().count("it87"), 1)

    def test_load_rejects_other_modules(self):
        h = tshelper.Helper("/", FakeRun({"modinfo": (0, "/lib/modules/x/kernel/drivers/net/foo.ko\n", "")}))
        self.assertFalse(h.load("foo", [], False, False)["ok"])
        self.assertFalse(h.load("../evil", [], False, False)["ok"])
        self.assertFalse(h.load("it87", ["x=1;rm"], False, False)["ok"])

    def test_grub_add_remove(self):
        with tempfile.TemporaryDirectory() as root:
            run = FakeRun()
            h = tshelper.Helper(root, run)
            self.assertTrue(h.grub(True)["ok"])
            path = os.path.join(root, ts.DROPIN.lstrip("/"))
            with open(path) as f:
                self.assertEqual(f.read(), ts.DROPIN_TEXT)
            self.assertIn(["update-grub"], run.calls)
            self.assertTrue(h.grub(False)["ok"])
            self.assertFalse(os.path.exists(path))

    def test_grub_failure_removes_file(self):
        with tempfile.TemporaryDirectory() as root:
            h = tshelper.Helper(root, FakeRun({"update-grub": (1, "", "error: syntax\n")}))
            r = h.grub(True)
            self.assertFalse(r["ok"])
            self.assertFalse(os.path.exists(os.path.join(root, ts.DROPIN.lstrip("/"))))


class WindowsCheckTests(unittest.TestCase):
    BASE = {"platform": "windows", "service": {"running": True}, "backend": "LibreHardwareMonitor 0.9.6.0 (PawnIO)",
            "pawnio": {"installed": True, "state": "RUNNING", "version": "2.2.0"}, "driver_events": [],
            "software": [], "laptop": False, "board": {"vendor": "Gigabyte Technology Co., Ltd.", "name": "X570 AORUS PRO"},
            "os": "Windows 10 22H2",
            "chips": [{"key": "it8689e", "name": "ITE IT8689E", "kind": "superio", "pwms": [1, 2, 3], "fans": [1, 2, 3],
                       "speed_only": []},
                      {"key": "it87952e", "name": "ITE IT87952E", "kind": "superio", "pwms": [1, 2], "fans": [1, 2, 3],
                       "speed_only": [3], "labels": {"3": "W_PUMP+"}}]}

    def test_gigabyte_two_chips_and_software(self):
        r = ts.windows_checks({**self.BASE, "software": ["Gigabyte Control Center"]})
        c = ids(r)
        self.assertIn("both were found, 5 controls", c["superio"]["detail"])
        self.assertIn("(W_PUMP+)", c["superio"]["detail"])
        self.assertEqual(c["software:Gigabyte Control Center"]["action"]["id"], "taskmgr")
        self.assertIn("gigabyte", c)
        self.assertEqual(r["summary"][0][0], "5 fan controls")

    def test_pawnio_and_service(self):
        r = ts.windows_checks({**self.BASE, "service": {"running": False}, "chips": [],
                               "pawnio": {"installed": False}})
        c = ids(r)
        self.assertEqual(c["service"]["action"]["id"], "service_on")
        self.assertEqual(c["pawnio"]["action"]["id"], "pawnio_repair")

    def test_laptop_opens_tips(self):
        r = ts.windows_checks({**self.BASE, "chips": [], "laptop": True, "board": {}})
        self.assertIn("laptop", ids(r))
        self.assertTrue(r["tips_open"])


class MarkdownTests(unittest.TestCase):
    def test_tips_files(self):
        here = os.path.join(os.path.dirname(__file__), "..", "src", "fankata", "tips")
        for name in ("linux.md", "windows.md"):
            with open(os.path.join(here, name), encoding="utf-8") as f:
                blocks = ts.markdown_blocks(f.read())
            self.assertGreaterEqual(sum(b["kind"] == "li" for b in blocks), 8, name)
        with open(os.path.join(here, "linux.md"), encoding="utf-8") as f:
            self.assertIn({"kind": "code", "text": "sudo apt install linux-generic-hwe-22.04"}, ts.markdown_blocks(f.read()))

    def test_report(self):
        r = ts.linux_checks(EMPTY)
        txt = ts.report_text(r, EMPTY, {"sensors-detect": SD_NCT})
        self.assertIn("[warn] No sensor chip with fan control", txt)
        self.assertIn("PRIME B550-PLUS", txt)
        self.assertIn("Nuvoton NCT6798D", txt)


if __name__ == "__main__":
    unittest.main()
