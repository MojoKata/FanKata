"""Simulated hardware: a fake hwmon sysfs tree matching the mockup machine.

Used by the tests, the demos and — on Windows — the service's developer
"simulate" mode (a VM has no fan controller). ``build(root)`` creates the tree;
``simulate(root, t)`` keeps it alive: temperatures drift and each fan's RPM follows
its pwm (or a firmware curve when pwm_enable != 1) with a realistic lag.

    python3 -m fankatad.simulate /tmp/fake --simulate
"""

from __future__ import annotations

import argparse
import math
import os
import random
import shutil
import time

# (hwmon index, device path, driver, temps [(n, label, m°C)], pwms [(n, enable, pwm)], fans [(n, label, max rpm)])
CHIPS = [
    (0, "devices/pci0000:00/0000:00:18.3", "k10temp", [(1, "Tctl", 54200), (3, "Tccd1", 51000)], [], []),
    (1, "devices/pci0000:00/0000:0a:00.0", "amdgpu", [(1, "edge", 48000), (2, "junction", 55000)], [], []),
    (2, "devices/pci0000:00/0000:01:00.0/nvme/nvme0", "nvme", [(1, "Composite", 41500)], [], []),
    (3, "devices/platform/nct6775.656", "nct6798",
     [(1, "SYSTIN", 36000), (2, "CPUTIN", 45000), (3, "AUXTIN0", 52300)],
     [(2, 5, 90), (3, 5, 77), (4, 5, 95), (6, 5, 128)],
     [(2, "", 2000), (3, "", 2000), (4, "", 2000)]),
    (4, "devices/pci0000:00/0000:00:14.0/usb1/1-9/1-9:1.0/0003:1E71:2007.0004", "nzxt-kraken3",
     [(1, "Coolant temp", 33900)], [(1, 2, 180), (2, 2, 80)], [(1, "Pump speed", 3600), (2, "Fan speed", 2200)]),
]


class Simulator:
    """Runs simulate() on a background thread (the Windows service's simulate mode)."""

    def __init__(self, root: str, period: float = 0.1):
        import threading
        self.root, self.period = root, period
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="simulator")

    def start(self) -> "Simulator":
        build(self.root)
        self._thread.start()
        return self

    def _run(self) -> None:
        t0 = time.monotonic()
        while not self._stop.wait(self.period):
            try:
                simulate(self.root, time.monotonic() - t0, dt=self.period)
            except OSError:
                pass

    def stop(self) -> None:
        self._stop.set()


def _dev(dev: str) -> str:
    """Device path; ':' isn't allowed in Windows file names."""
    return dev.replace(":", "_") if os.name == "nt" else dev


def _w(path: str, value) -> None:
    """Atomic, like real sysfs reads: readers never see a half-written file."""
    tmp = f"{path}.tmp{os.getpid()}"
    with open(tmp, "w") as f:
        f.write(f"{value}\n")
    os.replace(tmp, path)


def build(root: str) -> None:
    if os.path.exists(root):
        shutil.rmtree(root)
    cls = os.path.join(root, "sys/class/hwmon")
    os.makedirs(cls)
    for idx, dev, name, temps, pwms, fans in CHIPS:
        d = os.path.join(root, "sys", _dev(dev), "hwmon", f"hwmon{idx}")
        os.makedirs(d)
        _w(os.path.join(d, "name"), name)
        for n, label, v in temps:
            _w(os.path.join(d, f"temp{n}_input"), v)
            _w(os.path.join(d, f"temp{n}_label"), label)
        for n, en, pwm in pwms:
            _w(os.path.join(d, f"pwm{n}"), pwm)
            _w(os.path.join(d, f"pwm{n}_enable"), en)
        for n, label, mx in fans:
            _w(os.path.join(d, f"fan{n}_input"), 0)
            if label:
                _w(os.path.join(d, f"fan{n}_label"), label)
        link = os.path.join(cls, f"hwmon{idx}")
        try:
            os.symlink(os.path.relpath(d, cls), link, target_is_directory=True)
        except (OSError, NotImplementedError):     # Windows without symlink rights
            with open(link + ".path", "w") as f:
                f.write(d)
    simulate(root, 0.0, settle=True)


def _read(path: str, default: int = 0) -> int:
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return default


_rpm: dict[str, float] = {}


def simulate(root: str, t: float, dt: float = 0.1, settle: bool = False) -> None:
    for idx, dev, name, temps, pwms, fans in CHIPS:
        d = os.path.join(root, "sys", _dev(dev), "hwmon", f"hwmon{idx}")
        for n, label, v in temps:
            drift = 1500 * math.sin(t / 23 + idx + n) + 400 * math.sin(t / 4.1 + n)
            _w(os.path.join(d, f"temp{n}_input"), int(v + drift))
        for n, label, mx in fans:
            en = _read(os.path.join(d, f"pwm{n}_enable"), 1)
            pwm = _read(os.path.join(d, f"pwm{n}"), 0)
            if en == 1:
                duty = pwm / 255
            elif en == 0:
                duty = 1.0
            else:   # firmware curve: a gentle function of the chip's hottest sensor
                duty = min(1.0, max(0.3, (max(v for _, _, v in temps) / 1000 - 25) / 60)) if temps else 0.4
                _w(os.path.join(d, f"pwm{n}"), int(duty * 255))
            target = mx * (0.12 + 0.88 * duty)
            key = f"{idx}:{n}"
            cur = target if settle or key not in _rpm else _rpm[key]
            cur += (target - cur) * (1 - math.exp(-dt / 0.35))
            _rpm[key] = cur
            _w(os.path.join(d, f"fan{n}_input"), int(cur + random.uniform(-6, 6)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--simulate", action="store_true", help="keep updating values")
    a = ap.parse_args()
    build(a.root)
    print(f"fake sysfs at {a.root}", flush=True)
    t0 = time.monotonic()
    while a.simulate:
        time.sleep(0.1)
        simulate(a.root, time.monotonic() - t0)


if __name__ == "__main__":
    main()
