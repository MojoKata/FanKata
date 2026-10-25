"""Troubleshoot fans (requirement 4.7): turn facts about the PC into checks.

Facts are plain dicts so they can come from anywhere: the GUI collects them on
Linux (`linux_facts`, unprivileged), the service collects them on Windows (the
`diagnose` command), and the root helper adds what needs root (a `sensors-detect`
scan, a driver load). `linux_checks` / `windows_checks` turn them into the rows of
the Troubleshoot dialog:

    {"id", "st": ok|warn|fail|info|wait, "title", "detail", "tag",
     "action": {"id", "label", "primary", "lock", "disabled"},
     "check": {"id", "label", "on"}, "code": [lines]}

`detail` and labels use a small inline Markdown subset (**bold**, `code`, *italic*).
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess

# --------------------------------------------------------------------------- shared

READ_ONLY_DRIVERS = {          # hwmon drivers that report sensors but can't drive a fan
    "asus_wmi_sensors": "ASUS WMI: reads sensors only",
    "asus_ec_sensors": "ASUS EC: reads sensors only",
    "gigabyte_wmi": "Gigabyte WMI: reads temperatures only",
    "k10temp": "CPU", "coretemp": "CPU", "zenpower": "CPU", "nvme": "drive", "acpitz": "ACPI",
    "drivetemp": "drive", "iwlwifi_1": "Wi-Fi", "pch_cannonlake": "chipset", "spd5118": "memory",
}
CONFLICT = re.compile(r"resource conflict|ACPI.*(conflict|in use)|error -16\b|-EBUSY|Device or resource busy", re.I)
COMMUNITY_IT87 = "https://github.com/frankcrawford/it87"
COMMUNITY_IT87_STEPS = ["sudo apt install dkms git build-essential linux-headers-$(uname -r)",
                        f"git clone {COMMUNITY_IT87}",
                        "cd it87 && sudo make dkms"]
DROPIN = "/etc/default/grub.d/fankata.cfg"
LAX = "acpi_enforce_resources=lax"
DROPIN_TEXT = ("# Added by Fankata (Troubleshoot fans). Delete this file and run\n"
               "# sudo update-grub to undo.\n"
               f'GRUB_CMDLINE_LINUX_DEFAULT="$GRUB_CMDLINE_LINUX_DEFAULT {LAX}"\n')
MODULES_LOAD = "/etc/modules-load.d/fankata.conf"
MODPROBE_D = "/etc/modprobe.d/fankata.conf"
MODULE_NAME = re.compile(r"^[a-z0-9_]{2,40}$")
OPTION = re.compile(r"^[a-z0-9_]{1,40}=[A-Za-z0-9_.,-]{1,40}$")


def chips_from_inventory(inv) -> list[dict]:
    """One entry per sensor chip: its fan controls, fan speed inputs and which fans only report speed."""
    out = []
    for c in inv.chips:
        pwms = sorted(p.index for p in inv.pwms.values() if p.chip == c.key)
        fans = sorted(t.index for t in inv.tachs.values() if t.chip == c.key)
        temps = sum(1 for t in inv.temps if t.chip == c.key)
        out.append({"key": c.key, "name": c.name, "pwms": pwms, "fans": fans, "temps": temps,
                    "speed_only": [n for n in fans if n not in pwms]})
    return out


def _plural(n: int, word: str, many: str | None = None) -> str:
    return f"{n} {word if n == 1 else (many or word + 's')}"


def _codes(names) -> str:
    return ", ".join(f"`{n}`" for n in names)


def _speed_only(chips: list[dict]) -> list[str]:
    return [f"fan{n} on {c['key']}" for c in chips for n in c.get("speed_only", [])]


def markdown_blocks(md: str) -> list[dict]:
    """The tips' Markdown subset: ### headings, - bullets, ``` code blocks, paragraphs."""
    blocks, lines, i = [], md.strip("\n").split("\n"), 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            code = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i])
                i += 1
            blocks.append({"kind": "code", "text": "\n".join(code)})
        elif ln.startswith("### "):
            blocks.append({"kind": "h", "text": ln[4:].strip()})
        elif ln.startswith("- "):
            text = ln[2:].strip()
            while i + 1 < len(lines) and lines[i + 1].startswith("  ") and lines[i + 1].strip():
                i += 1
                text += " " + lines[i].strip()
            blocks.append({"kind": "li", "text": text})
        elif ln.strip() and not ln.startswith("#"):
            blocks.append({"kind": "p", "text": ln.strip()})
        i += 1
    return blocks


def tips_count(md: str) -> int:
    return sum(1 for b in markdown_blocks(md) if b["kind"] == "li")


def report_text(result: dict, facts: dict, extra: dict | None = None) -> str:
    """Plain text for Copy report: the checks, then the facts they came from."""
    import json
    lines = ["Fankata: Troubleshoot fans", ""]
    for big, small in result.get("summary", []):
        lines.append(f"{big} ({small})" if small else big)
    lines.append("")
    marks = {"ok": "[ok]  ", "warn": "[warn]", "fail": "[fail]", "info": "[info]", "wait": "[ -- ]"}
    for c in result.get("checks", []):
        lines.append(f"{marks.get(c['st'], '[    ]')} {c['title']}")
        if c.get("detail"):
            lines.append("       " + re.sub(r"\*\*|`|\*", "", c["detail"]))
    lines += ["", "Facts:", json.dumps(facts, indent=2, sort_keys=True, default=str)]
    for k, v in (extra or {}).items():
        if v:
            lines += ["", f"{k}:", v if isinstance(v, str) else json.dumps(v, indent=2, default=str)]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- Linux facts

def _read(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return None


def _os_release(etc: str) -> dict:
    out = {}
    for ln in (_read(os.path.join(etc, "os-release")) or _read("/usr/lib/os-release") or "").splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            out[k] = v.strip().strip('"')
    return out


def grub_cmdline(etc: str) -> dict:
    """GRUB_CMDLINE_LINUX(_DEFAULT) after /etc/default/grub and every grub.d/*.cfg, as grub-mkconfig sees them."""
    env = {"GRUB_CMDLINE_LINUX": "", "GRUB_CMDLINE_LINUX_DEFAULT": ""}
    files = [os.path.join(etc, "default", "grub")] + sorted(glob.glob(os.path.join(etc, "default", "grub.d", "*.cfg")))
    for path in files:
        for ln in (_read(path) or "").splitlines():
            m = re.match(r'\s*(GRUB_CMDLINE_LINUX(?:_DEFAULT)?)=(["\']?)(.*)\2\s*$', ln)
            if m:
                val = re.sub(r"\$\{?(GRUB_CMDLINE_LINUX(?:_DEFAULT)?)\}?", lambda v: env.get(v.group(1), ""), m.group(3))
                env[m.group(1)] = " ".join(val.split())
    return env


def grub_preview(etc: str = "/etc", remove: bool = False) -> dict:
    """What Add (or Remove) boot option will change: each file and the boot options, before and after."""
    path = os.path.join(etc, DROPIN.lstrip("/").split("/", 1)[1])
    current = _read(path)
    before = grub_cmdline(etc)
    cmd_before = " ".join(x for x in (before["GRUB_CMDLINE_LINUX"], before["GRUB_CMDLINE_LINUX_DEFAULT"]) if x)
    words = cmd_before.split()
    if remove:
        after_words = [w for w in words if w != LAX]
    else:
        after_words = words + ([] if LAX in words else [LAX])
    return {"file": DROPIN, "remove": remove,
            "before": current.splitlines() if current is not None else None,
            "after": None if remove else DROPIN_TEXT.rstrip("\n").splitlines(),
            "cmd_before": cmd_before, "cmd_after": " ".join(after_words), "added": [] if remove else [LAX]}


def _run(argv: list[str], timeout: float = 10) -> tuple[int, str]:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return 127, str(e)


def module_info(name: str) -> dict:
    """Is a kernel module installed, where from, and which parameters does it take (unprivileged)."""
    code, out = _run(["modinfo", "-F", "filename", name])
    if code != 0 or not out.strip():
        return {"available": False}
    filename = out.strip().splitlines()[0]
    _, params = _run(["modinfo", "-F", "parm", name])
    return {"available": True, "builtin": filename == "(builtin)", "filename": filename,
            "dkms": "/updates/" in filename or "/extra/" in filename,
            "params": sorted({p.split(":", 1)[0].strip() for p in params.splitlines() if ":" in p})}


def kernel_log() -> list[str] | None:
    """Kernel messages from this boot, unprivileged where the journal allows it (adm group on Ubuntu)."""
    for argv in (["journalctl", "-k", "-b", "-q", "--no-pager", "-o", "cat"], ["dmesg"]):
        code, out = _run(argv, timeout=15)
        if code == 0 and out.strip() and "Operation not permitted" not in out:
            return out.splitlines()
    return None


def relevant_log(lines: list[str] | None) -> list[str]:
    pat = re.compile(r"nct6\d+|it87|f71882|w836|thinkpad_acpi|dell_smm|asus|gigabyte|hwmon|ACPI.*(conflict|resource)", re.I)
    return [ln for ln in (lines or []) if pat.search(ln)][-40:]


def linux_facts(root: str = "/", service: dict | None = None, inv=None, probe=True) -> dict:
    """Unprivileged facts about this Linux PC. `root` prefixes /sys, /proc and /etc (tests and demos)."""
    from . import hwmon
    j = lambda *p: os.path.join(root, *p)  # noqa: E731
    inv = inv or hwmon.scan(root)
    dmi = lambda f: (_read(j("sys/class/dmi/id", f)) or "").strip()  # noqa: E731
    osr = _os_release(j("etc"))
    modules = sorted({ln.split()[0] for ln in (_read(j("proc/modules")) or "").splitlines() if ln.strip()})
    kernel = _read(j("proc/sys/kernel/osrelease")) or (os.uname().release if hasattr(os, "uname") else "")
    sb = None
    for f in glob.glob(j("sys/firmware/efi/efivars/SecureBoot-*")):
        try:
            with open(f, "rb") as fh:
                sb = fh.read()[-1:] == b"\x01"
        except OSError:
            pass
    nvidia = False
    for d in glob.glob(j("sys/bus/pci/devices/*")):
        if (_read(os.path.join(d, "vendor")) or "") == "0x10de" and (_read(os.path.join(d, "class")) or "").startswith("0x03"):
            nvidia = True
    facts = {
        "platform": "linux",
        "service": service or {"running": False},
        "chips": chips_from_inventory(inv),
        "board": {"vendor": dmi("board_vendor"), "name": dmi("board_name"), "product": dmi("product_name"),
                  "chassis": dmi("chassis_type")},
        "kernel": kernel,
        "os": osr.get("PRETTY_NAME", ""), "os_id": osr.get("ID", ""), "os_version": osr.get("VERSION_ID", ""),
        "modules": modules,
        "lm_sensors": bool(shutil.which("sensors-detect") or os.path.exists("/usr/sbin/sensors-detect")),
        "apt": bool(shutil.which("apt-get")),
        "secure_boot": sb,
        "nvidia": nvidia,
        "thinkpad_fan_control": _read(j("sys/module/thinkpad_acpi/parameters/fan_control")),
        "proc_cmdline": _read(j("proc/cmdline")) or "",
        "grub": {"available": bool(shutil.which("update-grub")) and os.path.isdir(j("etc/default")),
                 "dropin": os.path.exists(j(DROPIN.lstrip("/")))},
        "module_info": {},
        "kernel_log": None,
    }
    if probe:
        cands = {"it87", "nct6775", "nct6683", "thinkpad_acpi"} | {m for m in modules if m in ("it87", "nct6775", "nct6683")}
        facts["module_info"] = {m: module_info(m) for m in sorted(cands)}
        facts["kernel_log"] = relevant_log(kernel_log()) if root == "/" else []
    return facts


# --------------------------------------------------------------------------- sensors-detect

# Answers fed to sensors-detect, in order: yes to the CPU/south-bridge and Super I/O scans,
# then no to everything else (IPMI, ISA, SMBus, "press ENTER", and writing any configuration).
# The IPMI question is skipped on laptops; the answers after the second are all "no", so the
# order still lines up.
SENSORS_DETECT_INPUT = "y\ny\n" + "n\n" * 30


def parse_sensors_detect(out: str) -> dict:
    """Chips and drivers from a sensors-detect run (lm-sensors 3.6)."""
    chips, unknown, notes = [], [], []
    family = ""
    for ln in out.splitlines():
        m = re.match(r"Trying family `(.+?)'\.\.\.\s+Yes", ln)
        if m:
            family = m.group(1)
        m = re.match(r"Found unknown chip with ID 0x([0-9a-f]{4})", ln)
        if m:
            cid = m.group(1).upper()
            guess = f"ITE IT{cid}E" if "ITE" in family and cid[:2] in ("86", "87") else f"{family or 'Unknown'} chip 0x{cid}"
            unknown.append({"id": "0x" + m.group(1), "family": family, "name": guess})
        m = re.match(r"Note: there is no driver for (.+) yet\.", ln)
        if m:
            notes.append(m.group(1))
    driver = None
    for ln in out.split("Now follows a summary", 1)[-1].splitlines():
        m = re.match(r"Driver `(.+?)'(.*):", ln)
        if m:
            driver = {"driver": m.group(1), "autoloaded": "autoloaded" in m.group(2), "builtin": "built-in" in m.group(2)}
            continue
        m = re.match(r"\s+(?:\* )?(?:ISA bus(?:, address (0x[0-9a-f]+))?)?\s*$", ln)
        addr = m.group(1) if m else None
        if addr and driver is not None:
            driver["address"] = addr
        m = re.search(r"Chip `(.+?)' \(confidence: (\d+)\)", ln)
        if m and driver is not None:
            chips.append({**driver, "chip": m.group(1).replace(" Super IO Sensors", "").replace(" Sensors", ""),
                          "confidence": int(m.group(2)), "superio": "Super IO" in m.group(1)})
            driver = {k: v for k, v in driver.items() if k != "address"}
    return {"chips": chips, "unknown": unknown, "no_driver": notes, "nothing": "no sensors were detected" in out}


# --------------------------------------------------------------------------- Linux checks

def _summary_linux(f: dict) -> list:
    chips = f.get("chips", [])
    n = sum(len(c["pwms"]) for c in chips)
    with_pwm = [c["key"] for c in chips if c["pwms"]]
    so = _speed_only(chips)
    b = f.get("board") or {}
    vendor = _vendor(b.get("vendor", ""))
    board = b.get("name") or b.get("product") or "Unknown board"
    kern = re.match(r"\d+\.\d+(\.\d+)?", f.get("kernel", "") or "")
    small = " · ".join(x for x in (vendor, f"kernel {kern.group(0)}" if kern else "",
                                   (f.get("os") or "").replace(" LTS", "")) if x)
    return [[_plural(n, "fan control"), ", ".join(with_pwm) if with_pwm else "pwm outputs found"],
            [f"{len(so)} speed-only", ", ".join(so[:3]) + ("…" if len(so) > 3 else "") if so else "fans without control"],
            [board, small]]


def _vendor(v: str) -> str:
    low = v.lower()
    for key, short in (("gigabyte", "Gigabyte"), ("asus", "ASUS"), ("micro-star", "MSI"), ("asrock", "ASRock"),
                       ("lenovo", "Lenovo"), ("dell", "Dell"), ("hewlett", "HP"), ("hp", "HP")):
        if key in low:
            return short
    return v


def is_gigabyte(f: dict) -> bool:
    return "gigabyte" in ((f.get("board") or {}).get("vendor", "") + (f.get("board") or {}).get("product", "")).lower()


def _persist_check(module: str, options: list[str], on: bool) -> dict:
    files = [f"`{MODULES_LOAD}`"] + ([f"`{MODPROBE_D}`"] if options else [])
    return {"id": f"persist:{module}", "on": on, "label": f"Also load it at every boot ({', '.join(files)})"}


def linux_checks(f: dict, scan: dict | None = None, load: dict | None = None, persist: bool = True) -> dict:
    checks: list[dict] = []
    add = checks.append
    chips = f.get("chips", [])
    n_pwm = sum(len(c["pwms"]) for c in chips)
    loaded = set(f.get("modules", []))
    minfo = f.get("module_info", {})
    svc = f.get("service") or {}
    gb = is_gigabyte(f)

    # 1. the service
    if svc.get("running"):
        add({"id": "service", "st": "ok", "title": "Fan control service is running",
             "detail": f"`fankatad` {svc.get('version') or ''} · {svc.get('hardware') or 'Linux hwmon'}".replace("  ", " ")})
    else:
        add({"id": "service", "st": "warn", "title": "Fan control service is off",
             "detail": "Fans are under firmware control. Turn it on to control them from Fankata.",
             "action": {"id": "service_on", "label": "Turn on", "primary": True}})

    # 2. what the kernel already exposes
    names = [c["name"] for c in chips]
    if n_pwm:
        with_pwm = [c for c in chips if c["pwms"]]
        add({"id": "chips", "st": "ok", "title": f"{_plural(n_pwm, 'fan control')} found",
             "detail": "On " + ", ".join(f"`{c['key']}` ({len(c['pwms'])})" for c in with_pwm) + "."})
    else:
        desc = ", ".join(f"`{c['name']}`" + (f" ({READ_ONLY_DRIVERS[c['name']]})" if c["name"] in READ_ONLY_DRIVERS else "")
                         for c in chips)
        add({"id": "chips", "st": "warn", "title": "No sensor chip with fan control",
             "detail": f"Loaded: {desc}." if desc else "No hardware-monitoring driver is loaded."})
    so = _speed_only(chips)
    if so:
        add({"id": "speed_only", "st": "info", "title": f"{_plural(len(so), 'fan reports', 'fans report')} speed only",
             "detail": f"{', '.join(so)}: the chip reads their speed but has no control for them. "
                       "Check the header's mode in the BIOS (PWM or DC), or a hub or splitter they share."})

    # 3. kernel messages: a driver that couldn't claim its chip
    log = f.get("kernel_log")
    conflict_lines = [ln for ln in (load or {}).get("kernel_log", []) + (log or []) if CONFLICT.search(ln)]
    conflict_mod = None
    for ln in conflict_lines:
        m = re.search(r"\b(nct6\d+|it87|f71882fg|w83627ehf|nct6683)\b", ln)
        if m:
            conflict_mod = "nct6775" if m.group(1).startswith("nct67") else m.group(1)
            break

    # 4. lm-sensors and the scan
    if not f.get("lm_sensors"):
        add({"id": "lm_sensors", "st": "info" if n_pwm else "warn", "title": "lm-sensors isn’t installed",
             "detail": "It provides `sensors-detect`, which finds the board’s fan chip. "
                       "Installs the package `lm-sensors` with apt.",
             "action": {"id": "install_lm_sensors", "label": "Install lm-sensors", "primary": True, "lock": True,
                        "disabled": not f.get("apt")}})
    pending_load = None
    if scan is None:
        add({"id": "scan", "st": "wait", "tag": "Optional", "title": "Find the board’s fan chip",
             "detail": ("Runs `sensors-detect` for Super I/O and CPU sensors only. It skips the riskier SMBus and ISA "
                        "probes and changes no settings. Asks for an administrator password.")
             if f.get("lm_sensors") else "Needs lm-sensors.",
             "action": {"id": "scan", "label": "Scan", "lock": True, "primary": bool(f.get("lm_sensors")) and not n_pwm,
                        "disabled": not f.get("lm_sensors")}})
    elif scan.get("error"):
        add({"id": "scan", "st": "fail", "title": "The scan didn’t finish", "detail": scan["error"],
             "action": {"id": "scan", "label": "Scan again", "lock": True}})
    else:
        superio = [c for c in scan.get("chips", []) if c.get("superio")]
        unknown = scan.get("unknown", [])
        if not superio and not unknown:
            laptop = (f.get("board") or {}).get("chassis") in ("8", "9", "10", "14", "31", "32")
            add({"id": "scan", "st": "warn", "title": "No fan chip found",
                 "detail": "`sensors-detect` found no Super I/O chip. " +
                           ("On laptops the embedded controller usually runs the fans, out of reach of Linux."
                            if laptop else "Some OEM boards control fans only in firmware.")})
        for c in superio:
            drv = c["driver"]
            title = f"Found a{'n' if c['chip'][:1] in 'AEIOU' else ''} {c['chip']} Super I/O chip"
            addr = f", ISA address {c['address']}" if c.get("address") else ""
            if drv == "to-be-written":
                ite = c["chip"].startswith("ITE")
                add({"id": f"chip:{c['chip']}", "st": "fail", "title": title,
                     "detail": f"`sensors-detect` knows no Linux driver for it{addr}." +
                               (" ITE chips are supported by the community `it87` driver." if ite else ""),
                     **({"code": COMMUNITY_IT87_STEPS} if ite and not minfo.get("it87", {}).get("dkms") else {})})
                continue
            info = minfo.get(drv, {"available": None})
            is_loaded = drv in loaded or info.get("builtin")
            if is_loaded:
                st, detail = ("ok", f"Driver `{drv}`{addr} is loaded.") if n_pwm else \
                    ("warn", f"Driver `{drv}`{addr} is loaded, but it exposes no fan control.")
                add({"id": f"chip:{c['chip']}", "st": st, "title": title, "detail": detail})
            elif info.get("available") is False:
                add({"id": f"chip:{c['chip']}", "st": "fail", "title": title,
                     "detail": f"It needs driver `{drv}`, which isn’t installed for this kernel." +
                               (" Install the community `it87` driver." if drv == "it87" else ""),
                     **({"code": COMMUNITY_IT87_STEPS} if drv == "it87" else {})})
            else:
                add({"id": f"chip:{c['chip']}", "st": "ok", "title": title,
                     "detail": f"`sensors-detect`: driver `{drv}`{addr} (confidence {c.get('confidence', '?')}). "
                               "The driver is installed but not loaded."})
                pending_load = pending_load or drv
        for u in unknown:
            ite = u["name"].startswith("ITE")
            add({"id": f"chip:{u['id']}", "st": "fail" if not minfo.get("it87", {}).get("dkms") else "info",
                 "title": f"Found {u['name']}, which this sensors-detect doesn’t know",
                 "detail": (f"Chip ID {u['id']}. " +
                            ("Newer ITE chips (common on Gigabyte boards) need the community `it87` driver. "
                             "It builds against your kernel with DKMS and rebuilds after kernel updates."
                             if ite else "Check whether a driver exists for it.")),
                 **({"code": COMMUNITY_IT87_STEPS} if ite and not minfo.get("it87", {}).get("dkms") else {})})
            if ite and minfo.get("it87", {}).get("available") and "it87" not in loaded:
                pending_load = pending_load or "it87"

    # 5. load a driver (or reload it without the conflict)
    if load:
        mod = load.get("module", "")
        if not load.get("ok"):
            add({"id": f"load:{mod}", "st": "fail", "title": f"Couldn’t load {mod}",
                 "detail": load.get("error") or "modprobe failed.", "action": {"id": f"load:{mod}", "label": "Try again", "lock": True}})
        elif n_pwm:
            add({"id": f"load:{mod}", "st": "ok", "title": f"{mod} is loaded",
                 "detail": f"{_plural(n_pwm, 'fan control')} appeared." +
                           (" It loads at every boot." if load.get("persist") else "")})
            pending_load = None
        elif not conflict_lines:
            add({"id": f"load:{mod}", "st": "warn", "title": f"{mod} loaded, but no fan controls appeared",
                 "detail": "The driver didn’t find a chip it can drive."})
            pending_load = None
    if pending_load and not (load and load.get("ok") and load.get("module") == pending_load):
        add({"id": f"load:{pending_load}", "st": "info", "title": f"Load the {pending_load} driver",
             "detail": "Loads it now, then restarts the service so the fans appear.",
             "check": _persist_check(pending_load, [], persist),
             "action": {"id": f"load:{pending_load}", "label": "Load driver", "primary": True, "lock": True}})

    # 6. the firmware won't share the chip
    dropin = (f.get("grub") or {}).get("dropin")
    lax_active = LAX in (f.get("proc_cmdline") or "").split()
    if conflict_lines and not n_pwm:
        mod = conflict_mod or (load or {}).get("module") or "the driver"
        params = minfo.get(mod, {}).get("params", [])
        if "ignore_resource_conflict" in params and not lax_active:
            add({"id": "conflict", "st": "fail", "title": "The firmware won’t share the chip",
                 "detail": f"`{mod}` loaded, but the kernel says: *{_short(conflict_lines[-1])}*."})
            add({"id": f"reload:{mod}", "st": "info", "title": f"Load {mod} without a boot option",
                 "detail": f"Reloads `{mod}` with `ignore_resource_conflict=1`, so only the fan chip is shared with the firmware.",
                 "check": _persist_check(mod, ["ignore_resource_conflict=1"], persist),
                 "action": {"id": f"reload:{mod}:ignore_resource_conflict=1", "label": "Load driver", "primary": True, "lock": True}})
        elif not lax_active and not dropin:
            grub = (f.get("grub") or {}).get("available")
            add({"id": "conflict", "st": "fail", "title": "The firmware won’t share the chip",
                 "detail": f"`{mod}` loaded, but the kernel says: *{_short(conflict_lines[-1])}*. "
                           + ("Fankata can fix it only by adding a boot option." if grub else
                              f"Add `{LAX}` to your boot loader’s kernel options and restart."),
                 **({"action": {"id": "grub_add", "label": "Add boot option…", "lock": True}} if grub else {})})
    if dropin:
        add({"id": "grub", "st": "ok" if lax_active else "info",
             "title": "Boot option is active" if lax_active else "Restart to use the boot option",
             "detail": f"`{DROPIN}` adds `{LAX}`." + ("" if lax_active else " It takes effect after a restart."),
             "action": {"id": "grub_remove", "label": "Remove boot option…", "lock": True}})
    if log is None:
        add({"id": "kernel_log", "st": "wait", "title": "Kernel messages weren’t readable",
             "detail": "Fankata looks there for drivers that couldn’t claim their chip. They’re checked again after a scan or a driver load."})

    # 7. known machines
    if gb:
        add({"id": "gigabyte", "st": "info", "title": "Gigabyte board",
             "detail": "Gigabyte boards use ITE chips, often two: IT8686E, IT8688E, IT8689E or IT8696E for most headers, "
                       "plus IT8792E or IT87952E for the rest. `gigabyte_wmi` only reads temperatures. "
                       "Load `it87` with `ignore_resource_conflict=1` rather than a boot option."})
        it87 = minfo.get("it87", {})
        if not n_pwm and not it87.get("dkms") and not any(c.get("code") for c in checks):
            add({"id": "community_it87", "st": "info", "title": "Install the community it87 driver",
                 "detail": "The kernel’s own `it87` doesn’t know Gigabyte’s newer ITE chips. "
                           "The community driver builds with DKMS and rebuilds after kernel updates.",
                 "code": COMMUNITY_IT87_STEPS})
    if f.get("secure_boot") and any(c.get("code") == COMMUNITY_IT87_STEPS for c in checks):
        add({"id": "secure_boot", "st": "info", "title": "Secure Boot is on",
             "detail": "While installing, DKMS asks you to choose a password; on the next restart a blue "
                       "*MOK management* screen asks for it, to trust the new driver."})
    if f.get("thinkpad_fan_control") in ("N", "0"):
        add({"id": "thinkpad", "st": "info", "title": "ThinkPad fan control is turned off",
             "detail": "`thinkpad_acpi` only offers fan control with `fan_control=1`.",
             "check": _persist_check("thinkpad_acpi", ["fan_control=1"], persist),
             "action": {"id": "reload:thinkpad_acpi:fan_control=1", "label": "Turn it on", "primary": True, "lock": True}})
    if f.get("nvidia"):
        add({"id": "nvidia", "st": "info", "title": "NVIDIA graphics card",
             "detail": "Its fans can’t be controlled through Linux’s hwmon interface, so they don’t appear here."})
    kmaj = re.match(r"(\d+)\.(\d+)", f.get("kernel") or "")
    if (not n_pwm and f.get("os_id") == "ubuntu" and f.get("os_version") == "22.04"
            and kmaj and (int(kmaj.group(1)), int(kmaj.group(2))) < (6, 0)):
        add({"id": "hwe", "st": "info", "title": "A newer kernel is available",
             "detail": "Ubuntu 22.04’s HWE kernel knows more boards and fan chips.",
             "code": ["sudo apt install linux-generic-hwe-22.04"]})

    actionable = any(c.get("action") and not c["action"].get("disabled") and c["action"]["id"] != "scan" for c in checks) \
        or any(c.get("code") for c in checks)
    fixed = n_pwm > 0 and not so
    return {"platform": "linux", "summary": _summary_linux(f), "checks": checks,
            "lead": "Finds out why fans are missing, and fixes what it can.",
            "tips_open": bool(scan) and not actionable and not fixed,
            "tips_note": "" if not (scan and not actionable and not fixed) else "nothing more could be fixed automatically"}


def _short(line: str) -> str:
    line = re.sub(r"^\[\s*\d+\.\d+\]\s*", "", line).strip()
    return line if len(line) <= 110 else line[:107] + "…"


# --------------------------------------------------------------------------- Windows checks

FAN_SOFTWARE = {      # process name (lower case, no .exe) -> what it is
    "armourycrate.service": "Armoury Crate", "armourycrate.usersessionhelper": "Armoury Crate",
    "lightingservice": "Armoury Crate (Aura)", "aisuite3": "ASUS AI Suite",
    "icue": "Corsair iCUE", "corsair.service": "Corsair iCUE",
    "nzxt cam": "NZXT CAM", "cam": "NZXT CAM", "cam_helper": "NZXT CAM",
    "msi.centralserver": "MSI Center", "msi center": "MSI Center", "msi_center": "MSI Center",
    "gigabytecontrolcenter": "Gigabyte Control Center", "gcc": "Gigabyte Control Center",
    "siv": "Gigabyte SIV", "easytuneengineservice": "Gigabyte EasyTune", "easytune": "Gigabyte EasyTune",
    "rgbfusion": "Gigabyte RGB Fusion", "gcc.service": "Gigabyte Control Center",
    "signalrgb": "SignalRGB", "fancontrol": "FanControl", "hwinfo64": "HWiNFO", "speedfan": "SpeedFan",
    "argusmonitor": "Argus Monitor", "aida64": "AIDA64",
}
CHECKED_SOFTWARE = ["Armoury Crate", "iCUE", "NZXT CAM", "MSI Center", "Gigabyte Control Center, SIV and EasyTune",
                    "SignalRGB", "FanControl", "HWiNFO", "SpeedFan"]
SOFTWARE_EFFECT = {
    "NZXT CAM": "It holds the USB link to NZXT coolers, so their pump and fans can’t be reached.",
    "Corsair iCUE": "It holds the USB link to Corsair coolers and Commander hubs, so their fans can’t be reached.",
    "Gigabyte Control Center": "Its Smart Fan module and SIV write to the same ITE chips, so they overwrite Fankata’s speeds.",
    "Gigabyte SIV": "It writes to the same ITE chips, so it overwrites Fankata’s speeds.",
    "Gigabyte EasyTune": "It writes to the same ITE chips, so it overwrites Fankata’s speeds.",
}


def windows_checks(f: dict) -> dict:
    checks: list[dict] = []
    add = checks.append
    svc = f.get("service") or {}
    chips = f.get("chips", [])
    n_pwm = sum(len(c["pwms"]) for c in chips)
    gb = is_gigabyte(f)
    if svc.get("running"):
        add({"id": "service", "st": "ok", "title": "Fan control service is running",
             "detail": (f.get("backend") or "") + " as LocalSystem"})
    else:
        add({"id": "service", "st": "fail", "title": "Fan control service is off",
             "detail": "Fankata reads and controls fans through its service. Turn it on to check the hardware.",
             "action": {"id": "service_on", "label": "Turn on", "primary": True}})
    if f.get("backend_error"):
        add({"id": "backend", "st": "fail", "title": "No hardware access", "detail": f["backend_error"]})
    p = f.get("pawnio") or {}
    events = f.get("driver_events") or []
    if f.get("simulated"):
        add({"id": "pawnio", "st": "info", "title": "Simulated hardware",
             "detail": "This install runs the service against simulated fans (developer option)."})
    elif not p.get("installed"):
        add({"id": "pawnio", "st": "fail", "title": "The PawnIO driver isn’t installed",
             "detail": "Fankata needs it to reach the fan chip. **Repair** runs its installer (UAC prompt).",
             "action": {"id": "pawnio_repair", "label": "Repair", "primary": True, "lock": True}})
    elif p.get("state") != "RUNNING":
        add({"id": "pawnio", "st": "fail", "title": "The PawnIO driver isn’t running",
             "detail": (f"State: {p.get('state') or 'unknown'}. " +
                        (f"Windows says: *{_short(events[0])}*" if events else "Event Viewer → System may say why.")),
             "action": {"id": "pawnio_repair", "label": "Repair", "lock": True}})
    else:
        add({"id": "pawnio", "st": "ok", "title": "PawnIO driver is running",
             "detail": f"Version {p.get('version') or '?'} · " +
                       ("no driver blocks in the event log" if not events else f"earlier: *{_short(events[0])}*")})
    superio = [c for c in chips if c.get("kind") == "superio"]
    if superio:
        names = " and ".join(c["name"] for c in superio)
        n = sum(len(c["pwms"]) for c in superio)
        so = [f"`fan{x}`" + (f" ({c['labels'].get(str(x))})" if c.get("labels", {}).get(str(x)) else "")
              for c in superio for x in c.get("speed_only", [])]
        detail = (f"{len(superio) > 1 and gb and 'Gigabyte boards drive their extra fan headers from the second chip; both were found, ' or ''}"
                  f"{_plural(n, 'control')}" + (" in all." if len(superio) > 1 else "."))
        if so:
            detail += f" {', '.join(so)} report speed only. Check their header mode in the BIOS."
        add({"id": "superio", "st": "ok" if n else "warn", "title": f"Super I/O: {names}", "detail": detail[0].upper() + detail[1:]})
    elif svc.get("running") and not f.get("simulated"):
        add({"id": "superio", "st": "warn", "title": "No Super I/O chip found",
             "detail": "LibreHardwareMonitor didn’t find a motherboard fan chip it supports. "
                       + ("Laptops and" if f.get("laptop") else "Some OEM PCs and") + " newer boards may not be supported yet."})
    elif f.get("simulated") and chips:
        add({"id": "superio", "st": "ok", "title": f"{_plural(n_pwm, 'fan control')} found",
             "detail": "On " + ", ".join(f"`{c['key']}` ({len(c['pwms'])})" for c in chips if c["pwms"]) + "."})
    other = [c for c in chips if c.get("kind") not in ("superio", None) and c.get("speed_only")]
    for c in other:
        add({"id": f"speed_only:{c['key']}", "st": "info", "title": f"{c['name']}: speed only",
             "detail": f"{_plural(len(c['speed_only']), 'fan')} report speed but can’t be controlled here."})
    procs = f.get("software") or []
    for name in procs:
        add({"id": f"software:{name}", "st": "warn", "title": f"{name} is running",
             "detail": SOFTWARE_EFFECT.get(name, "It can take over the fan chip or a cooler’s USB link.") +
                       " Quit it, including its tray icon, then **Run again**.",
             "action": {"id": "taskmgr", "label": "Open Task Manager", "icon": "link"}})
    if not procs and svc.get("running"):
        add({"id": "software", "st": "ok", "title": "No other fan software found",
             "detail": "Checked for " + ", ".join(CHECKED_SOFTWARE[:-1]) + " and " + CHECKED_SOFTWARE[-1] + "."})
    if f.get("laptop"):
        add({"id": "laptop", "st": "info", "title": "This is a laptop",
             "detail": "The embedded controller runs its fans; LibreHardwareMonitor can usually read their speeds but not set them."})
    if gb:
        add({"id": "gigabyte", "st": "info", "title": "Gigabyte BIOS fan settings",
             "detail": "In Smart Fan 5/6, set each header’s *Fan Control Mode* to PWM for 4-pin fans or Voltage for 3-pin fans. "
                       "*Full Speed* stops software control."})
    b = f.get("board") or {}
    so_all = [x for c in chips for x in c.get("speed_only", [])]
    summary = [[_plural(n_pwm, "fan control"), " + ".join(c["name"] for c in superio) or ("simulated" if f.get("simulated") else "no Super I/O control")],
               [f"{len(so_all)} speed-only", "every header can be controlled" if not so_all else
                ", ".join(f"fan{x}" for x in so_all[:3])],
               [b.get("name") or "Unknown board", " · ".join(x for x in (_vendor(b.get("vendor", "")), f.get("os", "")) if x)]]
    actionable = any(c.get("action") for c in checks)
    nothing = not n_pwm and not actionable
    return {"platform": "windows", "summary": summary, "checks": checks,
            "lead": "Finds out why fans are missing, and points to what can fix it.",
            "tips_open": nothing, "tips_note": "nothing more could be checked automatically" if nothing else ""}
