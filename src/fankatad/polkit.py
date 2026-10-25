"""Authorization for changes: polkit action org.fankata.control (requirement 1.8).

The caller's process comes from the socket's SO_PEERCRED. Checking by
pid + start time + uid (not pid alone) avoids pid-reuse races.
"""

from __future__ import annotations

import logging
import shutil
import subprocess

ACTION = "org.fankata.control"
log = logging.getLogger("fankatad")


def process_start_time(pid: int) -> int | None:
    try:
        with open(f"/proc/{pid}/stat") as f:
            stat = f.read()
    except OSError:
        return None
    # Field 2 (comm) may contain spaces and parens; fields after the last ')' start at field 3.
    rest = stat[stat.rfind(")") + 2:].split()
    try:
        return int(rest[19])   # field 22: starttime
    except (IndexError, ValueError):
        return None


class Authorizer:
    def __init__(self, enabled: bool = True, action: str = ACTION):
        self.enabled = enabled
        self.action = action

    def check(self, pid: int, uid: int) -> tuple[bool, str]:
        if not self.enabled or uid == 0:
            return True, ""
        pkcheck = shutil.which("pkcheck")
        if not pkcheck:
            return False, "polkit (pkcheck) is not installed."
        start = process_start_time(pid)
        if start is None:
            return False, "Can’t identify the requesting process."
        cmd = [pkcheck, "--action-id", self.action, "--process", f"{pid},{start},{uid}",
               "--allow-user-interaction"]
        try:
            r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            return False, "Authorization timed out."
        if r.returncode == 0:
            return True, ""
        if r.returncode == 3:
            return False, "Authorization was dismissed."
        log.info("pkcheck denied uid %s (exit %s): %s", uid, r.returncode, r.stderr.strip())
        return False, "Not authorized to change fan control."
