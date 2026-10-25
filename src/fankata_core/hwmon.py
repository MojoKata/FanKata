"""Kernel hwmon sysfs access: discovery, naming, reading and writing.

Every path is resolved under a configurable root, so tests and demos can run
against a fake sysfs tree (see tests/fakesysfs.py).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

AIO_DRIVERS = frozenset({"nzxt-kraken2", "nzxt-kraken3", "asus_rog_ryujin", "aquacomputer_d5next"})
CPU_DRIVERS = ("k10temp", "zenpower", "coretemp", "cpu_thermal")
GPU_DRIVERS = ("amdgpu", "nouveau", "radeon", "i915", "xe")


@dataclass
class Chip:
    key: str        # unique across the system: driver name, plus a number for duplicates
    name: str       # driver name from the `name` attribute
    path: str       # directory holding the attributes
    devpath: str    # stable device path, used to order duplicates


@dataclass
class TempSensor:
    probe: str      # "sys.<name>"
    chip: str
    index: int
    label: str
    path: str
    desc: str


@dataclass
class Tach:
    id: str         # "<chip>:fanN"
    chip: str
    index: int
    label: str
    path: str


@dataclass
class PwmChannel:
    id: str                  # "<chip>:pwmN" — stable across reboots
    chip: str
    driver: str
    index: int
    pwm_path: str
    enable_path: str | None
    tach_id: str | None      # the channel's own tach, if it has one
    label: str
    detected_type: str

    @property
    def driver_label(self) -> str:
        return f"{self.driver} · fan{self.index}" if self.tach_id else f"{self.driver} · pwm{self.index}"


@dataclass
class Inventory:
    chips: list[Chip] = field(default_factory=list)
    temps: list[TempSensor] = field(default_factory=list)
    aliases: dict[str, tuple[list[str], str]] = field(default_factory=dict)   # probe -> (source probes, desc)
    tachs: dict[str, Tach] = field(default_factory=dict)
    pwms: dict[str, PwmChannel] = field(default_factory=dict)

    @property
    def probe_names(self) -> frozenset[str]:
        return frozenset([t.probe for t in self.temps] + list(self.aliases))

    def probe_desc(self, name: str) -> str:
        if name in self.aliases:
            return self.aliases[name][1]
        t = next((t for t in self.temps if t.probe == name), None)
        return t.desc if t else ""


def _read(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return None


def read_int(path: str | None) -> int | None:
    if not path:
        return None
    s = _read(path)
    if s is None:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def write_int(path: str, value: int) -> None:
    """Raises OSError if the driver rejects the value."""
    with open(path, "w", encoding="ascii") as f:
        f.write(f"{int(value)}\n")


def slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    return s or "x"


def detect_type(driver: str, label: str, has_tach: bool) -> str:
    low = label.lower()
    if "pump" in low:
        return "pump"
    if driver in AIO_DRIVERS or "aio" in low or "cpu_opt" in low:
        return "aio"
    if not has_tach:
        return "generic"
    return "case"


def _attr_dir(hwmon_dir: str) -> str:
    if os.path.exists(os.path.join(hwmon_dir, "name")):
        return hwmon_dir
    dev = os.path.join(hwmon_dir, "device")
    if os.path.exists(os.path.join(dev, "name")):
        return dev
    return hwmon_dir


def scan(root: str = "/") -> Inventory:
    inv = Inventory()
    base = os.path.join(root, "sys/class/hwmon")
    try:
        entries = sorted(os.listdir(base), key=lambda e: (len(e), e))
    except OSError:
        return inv
    found = []
    for e in entries:
        d = os.path.join(base, e)
        if e.endswith(".path"):      # simulated tree on Windows, where it can't use symlinks
            d = _read(d) or d
        adir = _attr_dir(d)
        name = _read(os.path.join(adir, "name")) or e
        found.append((name, os.path.realpath(d), adir))
    # Unique, reboot-stable keys: duplicates are numbered in device-path order.
    by_name: dict[str, list] = {}
    for item in found:
        by_name.setdefault(item[0], []).append(item)
    for name, items in by_name.items():
        items.sort(key=lambda it: it[1])
        for i, (n, real, adir) in enumerate(items):
            inv.chips.append(Chip(n if i == 0 else f"{n}{i + 1}", n, adir, real))
    inv.chips.sort(key=lambda c: c.devpath)

    for chip in inv.chips:
        try:
            files = set(os.listdir(chip.path))
        except OSError:
            continue
        for f in sorted(files):
            m = re.fullmatch(r"temp(\d+)_input", f)
            if m:
                n = int(m.group(1))
                label = _read(os.path.join(chip.path, f"temp{n}_label")) or f"temp{n}"
                inv.temps.append(TempSensor(f"sys.{slug(chip.key)}_{slug(label)}", chip.key, n, label,
                                            os.path.join(chip.path, f), f"{label} · {chip.name}"))
            m = re.fullmatch(r"fan(\d+)_input", f)
            if m:
                n = int(m.group(1))
                label = _read(os.path.join(chip.path, f"fan{n}_label")) or ""
                tid = f"{chip.key}:fan{n}"
                inv.tachs[tid] = Tach(tid, chip.key, n, label, os.path.join(chip.path, f))
        for f in sorted(files, key=lambda f: (len(f), f)):
            m = re.fullmatch(r"pwm(\d+)", f)
            if not m:
                continue
            n = int(m.group(1))
            tid = f"{chip.key}:fan{n}"
            has_tach = tid in inv.tachs
            label = inv.tachs[tid].label if has_tach else ""
            en = f"pwm{n}_enable"
            inv.pwms[f"{chip.key}:pwm{n}"] = PwmChannel(
                f"{chip.key}:pwm{n}", chip.key, chip.name, n, os.path.join(chip.path, f),
                os.path.join(chip.path, en) if en in files else None,
                tid if has_tach else None, label, detect_type(chip.name, label, has_tach))

    _add_aliases(inv)
    return inv


def _add_aliases(inv: Inventory) -> None:
    names = {t.probe for t in inv.temps}

    def add(alias: str, sources: list[TempSensor], desc: str) -> None:
        if sources and alias not in names:
            inv.aliases[alias] = ([t.probe for t in sources], desc)

    cpu = []
    for drv in CPU_DRIVERS:
        chips = [c for c in inv.chips if c.name == drv]
        for c in chips:
            ts = [t for t in inv.temps if t.chip == c.key]
            pick = ([t for t in ts if t.label.lower().startswith("package")]
                    or [t for t in ts if t.label in ("Tctl", "Tdie")][:1] or ts[:1])
            cpu += pick
        if cpu:
            add("sys.cpu", cpu, f"CPU package{' average' if len(cpu) > 1 else ''} · {drv}")
            break
    for drv in GPU_DRIVERS:
        c = next((c for c in inv.chips if c.name == drv), None)
        if c:
            ts = [t for t in inv.temps if t.chip == c.key]
            pick = [t for t in ts if t.label.lower() == "edge"][:1] or ts[:1]
            add("sys.gpu", pick, f"GPU {pick[0].label.lower() if pick else ''} · {drv}".replace("  ", " "))
            break
    c = next((c for c in inv.chips if c.name == "nvme"), None)
    if c:
        ts = [t for t in inv.temps if t.chip == c.key]
        pick = [t for t in ts if t.label == "Composite"][:1] or ts[:1]
        add("sys.nvme", pick, f"Composite · {c.key}")
    cool = [t for t in inv.temps if "coolant" in t.label.lower() or "liquid" in t.label.lower()]
    if not cool:
        cool = [t for t in inv.temps if any(c.key == t.chip and c.name in AIO_DRIVERS for c in inv.chips)]
    add("sys.coolant", cool[:1], f"Liquid · {cool[0].chip}" if cool else "")


def read_temps(inv: Inventory) -> dict[str, float | None]:
    vals: dict[str, float | None] = {}
    for t in inv.temps:
        v = read_int(t.path)
        vals[t.probe] = v / 1000.0 if v is not None else None
    for alias, (sources, _) in inv.aliases.items():
        xs = [vals[s] for s in sources if vals.get(s) is not None]
        vals[alias] = sum(xs) / len(xs) if xs else None
    return vals


def read_rpms(inv: Inventory) -> dict[str, int | None]:
    return {tid: read_int(t.path) for tid, t in inv.tachs.items()}


def duty_to_pwm(duty: float) -> int:
    return max(0, min(255, int(round(duty * 255 / 100))))


def pwm_to_duty(pwm: int | None) -> int | None:
    return None if pwm is None else int(round(pwm * 100 / 255))
