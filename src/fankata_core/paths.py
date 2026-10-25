"""Platform locations for the configuration, service state and GUI ↔ service channel."""

from __future__ import annotations

import os

IS_WINDOWS = os.name == "nt"

if IS_WINDOWS:
    _DATA = os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "Fankata")
    CONFIG_PATH = os.path.join(_DATA, "config.toml")
    RUN_DIR = os.path.join(_DATA, "run")
    LOG_DIR = os.path.join(_DATA, "log")
    SIM_ROOT = os.path.join(_DATA, "sim")
    SOCKET_PATH = "fankata"                  # QLocalSocket name → \\.\pipe\fankata
    PIPE_PATH = r"\\.\pipe\fankata"
else:
    CONFIG_PATH = "/etc/fankata/config.toml"
    RUN_DIR = "/run/fankata"
    LOG_DIR = ""
    SIM_ROOT = ""
    SOCKET_PATH = "/run/fankata/fankata.sock"
    PIPE_PATH = ""
