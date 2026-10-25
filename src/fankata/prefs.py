"""Per-user view preferences in ~/.config/fankata/gui.json (requirement 9.2)."""

from __future__ import annotations

import json
import os

DEFAULTS = {"theme": "system", "probesPanelOpen": True, "fanOrder": []}


def _path() -> str:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "Fankata", "gui.json")
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "fankata", "gui.json")


def load() -> dict:
    try:
        with open(_path()) as f:
            data = json.load(f)
        return {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save(prefs: dict) -> None:
    p = _path()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w") as f:
            json.dump(prefs, f, indent=1)
        os.replace(tmp, p)
    except OSError:
        pass
