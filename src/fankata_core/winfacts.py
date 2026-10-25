"""Facts for Troubleshoot fans on Windows (requirement 4.7.4).

The service gathers them with its hardware list (the `diagnose` command); the app
gathers the same facts minus the hardware when the service is off. Nothing here
needs elevation except reading other users' processes, which the service can do.
"""

from __future__ import annotations

import csv
import io
import os
import re
import subprocess

from . import troubleshoot as ts

NO_WINDOW = 0x08000000      # CREATE_NO_WINDOW


def _run(argv: list[str], timeout: float = 15) -> str:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                           creationflags=NO_WINDOW if os.name == "nt" else 0)
        return p.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _reg(path: str, name: str) -> str:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as k:
            return str(winreg.QueryValueEx(k, name)[0]).strip()
    except OSError:
        return ""


def board() -> dict:
    p = r"HARDWARE\DESCRIPTION\System\BIOS"
    return {"vendor": _reg(p, "BaseBoardManufacturer"), "name": _reg(p, "BaseBoardProduct"),
            "product": _reg(p, "SystemProductName")}


def os_name() -> str:
    p = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
    build = _reg(p, "CurrentBuild")
    name = "Windows 11" if build.isdigit() and int(build) >= 22000 else "Windows 10"
    return " ".join(x for x in (name, _reg(p, "DisplayVersion")) if x)


def pawnio() -> dict:
    version = _reg(r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PawnIO", "DisplayVersion")
    out = _run(["sc.exe", "query", "PawnIO"])
    m = re.search(r"STATE\s*:\s*\d+\s+(\w+)", out)
    return {"installed": bool(version) or bool(m), "version": version, "state": m.group(1) if m else None}


def driver_events() -> list[str]:
    """Recent System / Code Integrity events that mention PawnIO (a driver Windows refused to start)."""
    out = []
    for log, q in (("System", "*[System[Provider[@Name='Service Control Manager'] and (EventID=7000 or EventID=7026)]]"),
                   ("Microsoft-Windows-CodeIntegrity/Operational", "*[System[(EventID=3033 or EventID=3077 or EventID=3089)]]")):
        txt = _run(["wevtutil", "qe", log, f"/q:{q}", "/c:30", "/rd:true", "/f:text"])
        for block in txt.split("Event["):
            if "pawnio" in block.lower():
                m = re.search(r"Description:\s*\n?(.+)", block)
                out.append(" ".join((m.group(1) if m else block).split())[:200])
    return out[:5]


def software() -> list[str]:
    """Other fan, RGB or monitoring software that's running (names from troubleshoot.FAN_SOFTWARE)."""
    found = []
    for row in csv.reader(io.StringIO(_run(["tasklist", "/fo", "csv", "/nh"]))):
        if not row:
            continue
        name = row[0].lower()
        name = name[:-4] if name.endswith(".exe") else name
        what = ts.FAN_SOFTWARE.get(name)
        if what and what not in found:
            found.append(what)
    return found


def has_battery() -> bool:
    try:
        import ctypes

        class SPS(ctypes.Structure):
            _fields_ = [("ACLineStatus", ctypes.c_byte), ("BatteryFlag", ctypes.c_byte),
                        ("BatteryLifePercent", ctypes.c_byte), ("SystemStatusFlag", ctypes.c_byte),
                        ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]
        s = SPS()
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s)):
            return False
        flag = s.BatteryFlag & 0xFF
        return flag not in (128, 255)
    except Exception:
        return False


def windows_facts(service: dict | None = None, chips: list | None = None, backend: str = "",
                  backend_error: str = "", simulated: bool = False) -> dict:
    return {"platform": "windows", "service": service or {"running": False}, "chips": chips or [],
            "backend": backend, "backend_error": backend_error, "simulated": simulated,
            "pawnio": pawnio(), "driver_events": driver_events(), "software": software(),
            "laptop": has_battery(), "board": board(), "os": os_name()}
