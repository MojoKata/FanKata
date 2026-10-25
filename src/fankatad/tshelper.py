"""fankata-troubleshoot: the root half of Troubleshoot fans on Linux (requirement 4.7.3).

Run by the app through pkexec (polkit action org.fankata.troubleshoot, which asks for
an administrator password). Each subcommand does one fixed job and prints one JSON
object on stdout:

    scan                      sensors-detect, Super I/O and CPU probes only; changes nothing
    load MODULE [--option K=V]... [--persist] [--reload]
                              modprobe a hwmon driver, optionally at every boot; restarts fankata
    install-lm-sensors        apt-get install lm-sensors
    grub-add | grub-remove    write or delete /etc/default/grub.d/fankata.cfg, then update-grub
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

from fankata_core import troubleshoot as ts

ALLOWED_DIRS = ("/drivers/hwmon/", "/drivers/platform/x86/", "/updates/", "/extra/")


def _run(argv, input=None, timeout=60, env=None):
    try:
        p = subprocess.run(argv, input=input, capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, **(env or {})})
        return p.returncode, p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", f"{argv[0]} took too long."
    except OSError as e:
        return 127, "", f"Couldn’t run {argv[0]}: {e.strerror}"


class Helper:
    def __init__(self, root: str = "/", run=_run):
        self.root, self.run = root, run

    def path(self, p: str) -> str:
        return os.path.join(self.root, p.lstrip("/"))

    def kernel_lines(self) -> list[str]:
        code, out, _ = self.run(["dmesg"], timeout=15)
        return out.splitlines() if code == 0 else []

    # --- scan --------------------------------------------------------------------
    def scan(self) -> dict:
        code, out, err = self.run(["sensors-detect"], input=ts.SENSORS_DETECT_INPUT, timeout=180)
        if code == 127:
            return {"ok": False, "error": "sensors-detect isn’t installed (package lm-sensors)."}
        if code not in (0, 1, 255) and not out:
            return {"ok": False, "error": (err or out).strip()[-300:] or f"sensors-detect failed (exit {code})."}
        return {"ok": True, "scan": ts.parse_sensors_detect(out), "kernel_log": ts.relevant_log(self.kernel_lines()),
                "raw": out[-6000:]}

    # --- load a driver -------------------------------------------------------------
    def load(self, module: str, options: list[str], persist: bool, reload: bool) -> dict:
        if not ts.MODULE_NAME.match(module) or not all(ts.OPTION.match(o) for o in options):
            return {"ok": False, "module": module, "error": "Not a driver name Fankata loads."}
        code, out, _ = self.run(["modinfo", "-F", "filename", module])
        filename = out.strip().splitlines()[0] if code == 0 and out.strip() else ""
        if not filename:
            return {"ok": False, "module": module, "error": f"Driver {module} isn’t installed for this kernel."}
        if filename != "(builtin)" and not any(d in filename for d in ALLOWED_DIRS):
            return {"ok": False, "module": module, "error": f"{module} isn’t a hardware-monitoring driver."}
        before = len(self.kernel_lines())
        if reload:
            code, _, err = self.run(["modprobe", "-r", module])
            if code != 0:
                if persist and self._persist(module, options) is None:
                    return {"ok": False, "module": module, "restart": True,
                            "error": f"{module} is in use, so it can’t be reloaded now. It loads with the new options after a restart."}
                return {"ok": False, "module": module, "error": err.strip() or f"Couldn’t unload {module}."}
        code, _, err = self.run(["modprobe", module] + options)
        if code != 0:
            return {"ok": False, "module": module, "error": err.strip().splitlines()[-1] if err.strip() else f"modprobe {module} failed."}
        if persist:
            why = self._persist(module, options)
            if why:
                return {"ok": False, "module": module, "error": why}
        self.run(["systemctl", "try-restart", "fankata.service"], timeout=30)
        new = self.kernel_lines()[before:]
        return {"ok": True, "module": module, "options": options, "persist": persist,
                "kernel_log": ts.relevant_log(new) or new[-10:]}

    def _persist(self, module: str, options: list[str]) -> str | None:
        try:
            ml = self.path(ts.MODULES_LOAD)
            os.makedirs(os.path.dirname(ml), exist_ok=True)
            lines = _lines(ml) or ["# Added by Fankata (Troubleshoot fans): fan drivers to load at boot."]
            if module not in lines:
                lines.append(module)
            _write(ml, lines)
            mp = self.path(ts.MODPROBE_D)
            old = [ln for ln in _lines(mp) if not re.match(rf"options\s+{re.escape(module)}\s", ln)]
            if options:
                os.makedirs(os.path.dirname(mp), exist_ok=True)
                old = old or ["# Added by Fankata (Troubleshoot fans): fan driver options."]
                _write(mp, old + [f"options {module} {' '.join(options)}"])
            elif os.path.exists(mp):
                _write(mp, old)
        except OSError as e:
            return f"Couldn’t save the boot settings: {e.strerror}"
        return None

    # --- packages and boot options ------------------------------------------------------
    def install_lm_sensors(self) -> dict:
        code, out, err = self.run(["apt-get", "install", "-y", "-q", "lm-sensors"], timeout=900,
                                  env={"DEBIAN_FRONTEND": "noninteractive"})
        if code != 0:
            return {"ok": False, "error": (err or out).strip().splitlines()[-1] if (err or out).strip() else "apt-get failed."}
        return {"ok": True}

    def grub(self, add: bool) -> dict:
        f = self.path(ts.DROPIN)
        try:
            if add:
                os.makedirs(os.path.dirname(f), exist_ok=True)
                with open(f, "w", encoding="utf-8") as fh:
                    fh.write(ts.DROPIN_TEXT)
            elif os.path.exists(f):
                os.remove(f)
        except OSError as e:
            return {"ok": False, "error": f"Couldn’t write {ts.DROPIN}: {e.strerror}"}
        code, out, err = self.run(["update-grub"], timeout=300)
        if code != 0:
            if add:
                try:
                    os.remove(f)
                except OSError:
                    pass
            msg = (err or out).strip().splitlines()
            return {"ok": False, "error": "update-grub failed" + (f": {msg[-1]}" if msg else ".") +
                    (" The file was removed again." if add else "")}
        return {"ok": True, "restart": True}


def _lines(path: str) -> list[str]:
    try:
        with open(path, encoding="utf-8") as f:
            return [ln.rstrip("\n") for ln in f if ln.strip()]
    except OSError:
        return []


def _write(path: str, lines: list[str]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def main(argv: list[str] | None = None, helper: Helper | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fankata-troubleshoot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan")
    ld = sub.add_parser("load")
    ld.add_argument("module")
    ld.add_argument("--option", action="append", default=[])
    ld.add_argument("--persist", action="store_true")
    ld.add_argument("--reload", action="store_true")
    sub.add_parser("install-lm-sensors")
    sub.add_parser("grub-add")
    sub.add_parser("grub-remove")
    a = ap.parse_args(argv)
    h = helper or Helper()
    if a.cmd == "scan":
        r = h.scan()
    elif a.cmd == "load":
        r = h.load(a.module, a.option, a.persist, a.reload)
    elif a.cmd == "install-lm-sensors":
        r = h.install_lm_sensors()
    else:
        r = h.grub(a.cmd == "grub-add")
    print(json.dumps(r))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
