"""GUI ↔ service protocol: newline-delimited JSON over a Unix domain socket.

Requests:  {"id": 1, "cmd": "hello", "version": 1}
Replies:   {"id": 1, "ok": true, "result": {...}}  or  {"id": 1, "ok": false, "error": "...", "errors": [...]}
Events:    {"event": "state", "data": {...}}       (after "subscribe")

Commands: hello, get_state, subscribe, set_config {config}, pulse_start {fan}, pulse_stop,
service_disable (Windows: turn the service off; Linux uses fankata-servicectl via pkexec).
"""

from __future__ import annotations

import json

VERSION = 1
from .paths import SOCKET_PATH  # noqa: E402,F401  (a pipe name on Windows)
MAX_LINE = 4 * 1024 * 1024
WRITE_COMMANDS = frozenset({"set_config", "pulse_start", "pulse_stop", "service_disable"})


def encode(msg: dict) -> bytes:
    return (json.dumps(msg, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def decode(line: bytes | str) -> dict:
    msg = json.loads(line)
    if not isinstance(msg, dict):
        raise ValueError("message must be an object")
    return msg
