"""Windows backend: LibreHardwareMonitorLib (loaded through pythonnet) over the PawnIO driver.

LibreHardwareMonitor's tree (hardware → sub-hardware → sensors) is mapped onto the
same Inventory the Linux backend builds, so ids, probe names and aliases work the
same way:

- a Control sensor that has a settable IControl becomes a fan channel
  ("<chip>:pwm<N>"), paired with the Fan sensor of the same index ("<chip>:fan<N>");
- every Temperature sensor becomes "sys.<chip>_<label>", plus the sys.cpu /
  sys.gpu / sys.nvme / sys.coolant aliases.

Returning a channel to its default uses IControl.SetDefault(), which hands it back
to the firmware (LibreHardwareMonitor keeps the chip's original registers).
"""

from __future__ import annotations

import logging
import os

from fankata_core import hwmon
from fankata_core.hwmon import Chip, Inventory, PwmChannel, Tach, TempSensor

from . import Backend, BackendError

log = logging.getLogger("fankatad")
AIO_HINTS = ("kraken", "cooler", "aio")


def _key(hw) -> str:
    # the last non-numeric part of the identifier:
    # "/lpc/nct6798d/0" → "nct6798d", "/amdcpu/0" → "amdcpu", "/gpu-nvidia/0" → "gpu-nvidia"
    parts = [p for p in str(hw.Identifier).split("/") if p and not p.isdigit()]
    base = parts[-1] if parts else str(hw.Name)
    return hwmon.slug(base).replace("_", "-") or "hw"


class LhmBackend(Backend):
    name = "LibreHardwareMonitor"

    def __init__(self, lib_dir: str):
        import pythonnet
        pythonnet.load("netfx")          # .NET Framework 4.8 ships with Windows 10+
        import clr  # noqa: F401  (provided by pythonnet)
        clr.AddReference(os.path.join(lib_dir, "LibreHardwareMonitorLib.dll"))
        from LibreHardwareMonitor.Hardware import Computer, HardwareType, SensorType  # type: ignore
        self._SensorType, self._HardwareType = SensorType, HardwareType
        c = Computer()
        c.IsCpuEnabled = True
        c.IsGpuEnabled = True
        c.IsMotherboardEnabled = True
        c.IsControllerEnabled = True
        c.IsStorageEnabled = True
        c.IsPsuEnabled = True
        c.Open()
        self.computer = c
        self._version = str(c.GetType().Assembly.GetName().Version)
        self._temps: dict[str, object] = {}
        self._fans: dict[str, object] = {}
        self._controls: dict[str, object] = {}
        self._kinds: dict[str, str] = {}
        self.inv = self._scan()

    def describe(self) -> str:
        return f"LibreHardwareMonitor {self._version} (PawnIO)"

    # --- discovery ---------------------------------------------------------------
    def _walk(self):
        for hw in self.computer.Hardware:
            hw.Update()
            yield hw
            for sub in hw.SubHardware:
                sub.Update()
                yield sub

    def _scan(self) -> Inventory:
        ST, HT = self._SensorType, self._HardwareType
        inv = Inventory()
        seen: dict[str, int] = {}
        cpu, gpu, nvme, cool = [], [], [], []
        for hw in self._walk():
            base = _key(hw)
            seen[base] = seen.get(base, 0) + 1
            key = base if seen[base] == 1 else f"{base}{seen[base]}"
            name = str(hw.Name)
            inv.chips.append(Chip(key, name, str(hw.Identifier), str(hw.Identifier)))
            self._kinds[key] = str(hw.HardwareType).lower()
            fans = {int(s.Index): s for s in hw.Sensors if s.SensorType == ST.Fan}
            for s in hw.Sensors:
                label = str(s.Name)
                if s.SensorType == ST.Temperature:
                    probe = f"sys.{hwmon.slug(key)}_{hwmon.slug(label)}"
                    t = TempSensor(probe, key, int(s.Index), label, str(s.Identifier), f"{label} · {name}")
                    inv.temps.append(t)
                    self._temps[probe] = s
                    low = label.lower()
                    if hw.HardwareType == HT.Cpu:
                        cpu.append((("package" in low) or ("tctl" in low) or ("tdie" in low), t))
                    elif hw.HardwareType in (HT.GpuNvidia, HT.GpuAmd, HT.GpuIntel):
                        gpu.append(("core" in low, t))
                    elif hw.HardwareType == HT.Storage:
                        nvme.append(("nvme" in name.lower(), t))
                    if "liquid" in low or "coolant" in low or "water" in low:
                        cool.append(t)
                elif s.SensorType == ST.Fan:
                    tid = f"{key}:fan{int(s.Index) + 1}"
                    inv.tachs[tid] = Tach(tid, key, int(s.Index) + 1, label, str(s.Identifier))
                    self._fans[tid] = s
            for s in hw.Sensors:
                if s.SensorType != ST.Control or s.Control is None:
                    continue
                n = int(s.Index) + 1
                pid = f"{key}:pwm{n}"
                tach = fans.get(int(s.Index))
                tid = f"{key}:fan{n}" if tach is not None else None
                label = str(tach.Name) if tach is not None else str(s.Name)
                if "pump" in label.lower():
                    kind = "pump"
                elif hw.HardwareType == HT.Cooler or any(h in name.lower() for h in AIO_HINTS):
                    kind = "aio"
                elif tid is None:
                    kind = "generic"
                else:
                    kind = "case"
                inv.pwms[pid] = PwmChannel(pid, key, name, n, str(s.Identifier), None, tid, label, kind)
                self._controls[pid] = s

        def pick(cands, desc):
            best = [t for good, t in cands if good] or [t for _, t in cands]
            return best[:1], desc
        if cpu:
            srcs, _ = pick(cpu, "")
            inv.aliases["sys.cpu"] = ([t.probe for t in srcs], f"CPU package · {srcs[0].desc.split(' · ')[-1]}")
        if gpu:
            srcs, _ = pick(gpu, "")
            inv.aliases["sys.gpu"] = ([t.probe for t in srcs], f"GPU core · {srcs[0].desc.split(' · ')[-1]}")
        if nvme:
            srcs, _ = pick(nvme, "")
            inv.aliases["sys.nvme"] = ([t.probe for t in srcs], f"Drive · {srcs[0].desc.split(' · ')[-1]}")
        if cool:
            inv.aliases["sys.coolant"] = ([cool[0].probe], f"Liquid · {cool[0].desc.split(' · ')[-1]}")
        for a in list(inv.aliases):
            if a in {t.probe for t in inv.temps}:
                del inv.aliases[a]
        log.info("LibreHardwareMonitor %s: %d hardware, %d temperatures, %d fan controls",
                 self._version, len(inv.chips), len(inv.temps), len(inv.pwms))
        return inv

    # --- readings ----------------------------------------------------------------
    def refresh(self) -> None:
        for _ in self._walk():
            pass

    @staticmethod
    def _value(s):
        v = s.Value
        return None if v is None else float(v)

    def read_temps(self):
        vals = {p: self._value(s) for p, s in self._temps.items()}
        for alias, (sources, _) in self.inv.aliases.items():
            xs = [vals[x] for x in sources if vals.get(x) is not None]
            vals[alias] = sum(xs) / len(xs) if xs else None
        return vals

    def read_rpms(self):
        out = {}
        for tid, s in self._fans.items():
            v = self._value(s)
            out[tid] = None if v is None else int(round(v))
        return out

    def read_duty(self, pid):
        s = self._controls.get(pid)
        v = self._value(s) if s is not None else None
        return None if v is None else int(round(v))

    # --- control -----------------------------------------------------------------
    def write_duty(self, pid, duty):
        s = self._controls[pid]
        try:
            ctl = s.Control
            lo, hi = float(ctl.MinSoftwareValue), float(ctl.MaxSoftwareValue)
            ctl.SetSoftware(max(lo, min(hi, float(duty))))
        except Exception as e:  # .NET exceptions surface as System.Exception
            raise BackendError(f"Can’t set speed: {e}") from None

    def restore(self, pid, original):
        try:
            self._controls[pid].Control.SetDefault()
            return {"ok": True, "message": ""}
        except Exception as e:
            return {"ok": False, "message": f"Couldn’t return to firmware control: {e}"}

    def restore_mode(self, pid, original):
        return {"mode": "auto", "duty": None}

    def chips(self) -> list[dict]:
        out = super().chips()
        for c in out:
            c["kind"] = self._kinds.get(c["key"], "")
            c["labels"] = {str(t.index): t.label for t in self.inv.tachs.values() if t.chip == c["key"] and t.label}
        return out

    def close(self) -> None:
        try:
            self.computer.Close()
        except Exception:
            pass


class NullBackend(Backend):
    """No hardware access (e.g. the PawnIO driver is missing). The GUI shows why."""
    name = "none"
    unavailable = True

    def __init__(self, reason: str):
        self.reason = reason
        self.inv = Inventory()

    def describe(self):
        return self.reason

    def read_temps(self):
        return {}

    def read_rpms(self):
        return {}

    def read_duty(self, pid):
        return None

    def write_duty(self, pid, duty):
        raise BackendError(self.reason)

    def restore(self, pid, original):
        return {"ok": True, "message": ""}


