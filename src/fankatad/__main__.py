"""fankatad entry point."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import time

from fankata_core import __version__, protocol
from fankata_core.config import DEFAULT_PATH

from . import sdnotify
from .controller import Controller, restore_from_files
from .polkit import Authorizer
from .server import Server

log = logging.getLogger("fankatad")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fankatad", description="Fankata fan control service.")
    ap.add_argument("--sysfs-root", default="/", help="prefix for /sys (tests and demos)")
    ap.add_argument("--config", default=DEFAULT_PATH)
    ap.add_argument("--run-dir", default="/run/fankata")
    ap.add_argument("--socket", default=None, help=f"default: <run-dir>/{os.path.basename(protocol.SOCKET_PATH)}")
    ap.add_argument("--no-auth", action="store_true", help="skip polkit checks (development only)")
    ap.add_argument("--restore", action="store_true", help="return every touched fan to its default and exit")
    ap.add_argument("--version", action="version", version=f"fankatad {__version__}")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(levelname)s %(message)s" if os.environ.get("INVOCATION_ID")
                        else "%(asctime)s %(levelname)s %(message)s")

    if a.restore:
        return restore_from_files(a.sysfs_root, a.run_dir)

    ctl = Controller(a.sysfs_root, a.config, a.run_dir)
    server = Server(a.socket or os.path.join(a.run_dir, "fankata.sock"), ctl, Authorizer(enabled=not a.no_auth))
    stop = threading.Event()

    def on_signal(signum, _frame):
        log.info("received %s, stopping", signal.Signals(signum).name)
        stop.set()
        ctl.wake.set()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    serve(ctl, server, stop, sdnotify.notify)
    return 0


def serve(ctl, server, stop: threading.Event, notify=lambda msg: None) -> None:
    """The service main loop, shared by Linux (systemd) and the Windows service."""
    try:
        ctl.tick()
        server.start()
        log.info("fankatad %s: %d fans, %d probes (%s)", __version__, len(ctl.inv.pwms),
                 len(ctl.inv.probe_names), ctl.hw.describe())
        notify(f"READY=1\nSTATUS=Controlling {len(ctl.inv.pwms)} fans")
        while not stop.is_set():
            ctl.wake.wait(ctl.interval())
            ctl.wake.clear()
            if stop.is_set():
                break
            t0 = time.monotonic()
            ctl.tick()
            server.broadcast(ctl.state())
            notify("WATCHDOG=1")
            if time.monotonic() - t0 > 0.5:
                log.warning("tick took %.2fs", time.monotonic() - t0)
    finally:
        notify("STOPPING=1")
        server.close()
        ctl.restore_all()
        ctl.hw.close()
        log.info("all fans returned to their defaults")


if __name__ == "__main__":
    sys.exit(main())
