"""Linux kernel hwmon backend (sysfs), also used over a simulated sysfs tree."""

from __future__ import annotations

from fankata_core import hwmon

from . import Backend, BackendError


class HwmonBackend(Backend):
    name = "hwmon"

    def __init__(self, sysfs_root: str = "/"):
        self.root = sysfs_root
        self.inv = hwmon.scan(sysfs_root)

    def describe(self) -> str:
        return "Linux hwmon" if self.root == "/" else f"simulated hwmon ({self.root})"

    def read_temps(self):
        return hwmon.read_temps(self.inv)

    def read_rpms(self):
        return hwmon.read_rpms(self.inv)

    def read_duty(self, pid):
        return hwmon.pwm_to_duty(hwmon.read_int(self.inv.pwms[pid].pwm_path))

    def capture(self, pid):
        ch = self.inv.pwms[pid]
        return {"enable": hwmon.read_int(ch.enable_path), "pwm": hwmon.read_int(ch.pwm_path)}

    def take_control(self, pid):
        ch = self.inv.pwms[pid]
        if ch.enable_path and hwmon.read_int(ch.enable_path) != 1:
            try:
                hwmon.write_int(ch.enable_path, 1)
            except OSError as e:
                raise BackendError(f"Can’t switch to manual control: {e.strerror or e}.") from None

    def write_duty(self, pid, duty):
        ch = self.inv.pwms[pid]
        target = hwmon.duty_to_pwm(duty)
        if hwmon.read_int(ch.pwm_path) != target:
            try:
                hwmon.write_int(ch.pwm_path, target)
            except OSError as e:
                raise BackendError(f"Can’t set speed: {e.strerror or e}.") from None

    def restore_mode(self, pid, original):
        en, pwm = original.get("enable"), original.get("pwm")
        ch = self.inv.pwms[pid]
        if ch.enable_path and en is not None and en >= 2:
            return {"mode": "auto", "duty": None}
        if ch.enable_path and en == 0:
            return {"mode": "full", "duty": 100}
        if pwm is not None:
            return {"mode": "fixed", "duty": hwmon.pwm_to_duty(pwm)}
        return {"mode": "full", "duty": 100}

    def restore(self, pid, original):
        ch = self.inv.pwms[pid]
        en0, pwm0 = original.get("enable"), original.get("pwm")
        try:
            if ch.enable_path and en0 is not None and en0 != 1:
                try:
                    hwmon.write_int(ch.enable_path, en0)
                    if hwmon.read_int(ch.enable_path) != en0:
                        raise OSError(0, "the chip did not accept its original mode")
                except OSError as e:
                    hwmon.write_int(ch.enable_path, 1)
                    hwmon.write_int(ch.pwm_path, pwm0 if pwm0 is not None else 255)
                    return {"ok": False, "message": f"Couldn’t return to automatic mode ({e.strerror or e}); "
                                                    f"left at its original speed."}
            elif pwm0 is not None:
                if ch.enable_path:
                    hwmon.write_int(ch.enable_path, 1)
                hwmon.write_int(ch.pwm_path, pwm0)
            else:
                hwmon.write_int(ch.pwm_path, 255)
        except OSError as e:
            return {"ok": False, "message": f"Couldn’t restore the default state: {e.strerror or e}."}
        return {"ok": True, "message": ""}
