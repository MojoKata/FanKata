"""Read-only monitoring when the service can't be reached (requirement 1.10).

Sensors are world-readable in sysfs and /etc/fankata/config.toml is 0644, so the
GUI can still show live values and the saved assignments.
"""

from __future__ import annotations

import os

from fankata_core import config as cfgmod
from fankata_core import expr as exprmod
from fankata_core import hwmon

ALIAS_ORDER = ("sys.cpu", "sys.gpu", "sys.nvme", "sys.coolant")


class ReadOnlyPoller:
    def __init__(self, sysfs_root: str, config_path: str):
        self.root = sysfs_root
        self.config_path = config_path
        self.inv = hwmon.scan(sysfs_root)
        self._cfg_mtime = None
        self._seq = 0
        self.cfg = cfgmod.default_config()

    def rescan(self) -> None:
        """A driver was just loaded (Troubleshoot fans): look for new chips."""
        self.inv = hwmon.scan(self.root)

    def _config(self) -> cfgmod.Config:
        try:
            m = os.stat(self.config_path).st_mtime
            if m != self._cfg_mtime:
                self.cfg = cfgmod.load(self.config_path)
                self._cfg_mtime = m
        except Exception:
            pass
        return self.cfg

    def state(self) -> dict:
        cfg = self._config()
        temps = hwmon.read_temps(self.inv)
        rpms = hwmon.read_rpms(self.inv)
        ps = exprmod.ProbeSet(temps, {p.name: p.expr for p in cfg.probes})
        fans = []
        for pid, ch in self.inv.pwms.items():
            s = cfg.fan(pid)
            tach = s.rpm_sensor if s.rpm_sensor in self.inv.tachs else ch.tach_id
            fans.append({
                "id": pid, "chip": ch.chip, "driver": ch.driver, "index": ch.index,
                "name": s.name or ch.driver_label, "default_name": ch.driver_label,
                "driver_label": ch.driver_label + ("" if ch.tach_id else " · no tach"),
                "detected_type": ch.detected_type, "type": s.type or ch.detected_type,
                "type_overridden": bool(s.type), "rpm": rpms.get(tach) if tach else None, "rpm_sensor": tach,
                "duty": hwmon.pwm_to_duty(hwmon.read_int(ch.pwm_path)),
                "curve": s.curve, "probe": s.probe,
                "probe_value": ps.try_value(s.probe)[0] if s.probe else None,
                "managed": False, "status": "default",
                "message": "The Fankata service isn’t running." if s.curve else "",
                "restore": {"mode": "auto", "duty": None},
            })
        names = sorted(temps, key=lambda n: (n not in ALIAS_ORDER, ALIAS_ORDER.index(n) if n in ALIAS_ORDER else 0, n))
        probes = [{"name": n, "kind": "system", "desc": self.inv.probe_desc(n), "value": temps[n],
                   "error": None if temps[n] is not None else "Can’t be read."} for n in names]
        for p in cfg.probes:
            v, err = ps.try_value(p.name)
            probes.append({"name": p.name, "kind": "custom", "desc": p.expr, "expr": p.expr, "value": v, "error": err})
        self._seq += 1
        return {"service": {"version": None, "readonly": True}, "config": cfg.to_dict(), "fans": fans,
                "probes": probes, "tachs": [], "pulse": None, "last_pulse": None,
                "sample": {"seq": self._seq, "interval": 1.0}}
