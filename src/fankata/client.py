"""Socket client for fankatad: newline-delimited JSON over QLocalSocket, auto-reconnecting."""

from __future__ import annotations

import json
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QLocalSocket

from fankata_core import protocol


class ServiceClient(QObject):
    connected = Signal()
    disconnected = Signal()
    stateEvent = Signal(dict)

    def __init__(self, path: str, parent: QObject | None = None):
        super().__init__(parent)
        self.path = path
        self.sock = QLocalSocket(self)
        self.sock.connected.connect(self._on_connected)
        self.sock.disconnected.connect(self._on_disconnected)
        self.sock.errorOccurred.connect(self._on_error)
        self.sock.readyRead.connect(self._on_ready)
        self._buf = b""
        self._next_id = 1
        self._pending: dict[int, Callable[[dict], None]] = {}
        self.is_connected = False
        self.retry = QTimer(self, interval=2000, singleShot=True)
        self.retry.timeout.connect(self.connect_now)

    def connect_now(self) -> None:
        if self.sock.state() == QLocalSocket.LocalSocketState.UnconnectedState:
            self.sock.connectToServer(self.path)

    def request(self, cmd: str, cb: Callable[[dict], None] | None = None, **params) -> None:
        if not self.is_connected:
            if cb:
                cb({"ok": False, "error": "Not connected to the Fankata service."})
            return
        mid = self._next_id
        self._next_id += 1
        if cb:
            self._pending[mid] = cb
        self.sock.write(protocol.encode({"id": mid, "cmd": cmd, **params}))
        self.sock.flush()

    def _on_connected(self) -> None:
        self.is_connected = True
        self._buf = b""

        def on_hello(r: dict) -> None:
            if not r.get("ok") or not r["result"].get("compatible"):
                self.sock.disconnectFromServer()
                return
            self.request("subscribe", lambda s: s.get("ok") and self.stateEvent.emit(s["result"]))
            self.connected.emit()

        self.request("hello", on_hello, version=protocol.VERSION)

    def _on_disconnected(self) -> None:
        was = self.is_connected
        self.is_connected = False
        for cb in self._pending.values():
            cb({"ok": False, "error": "Lost the connection to the Fankata service."})
        self._pending.clear()
        if was:
            self.disconnected.emit()
        self.retry.start()

    def _on_error(self, _err) -> None:
        if not self.is_connected:
            self.retry.start()

    def _on_ready(self) -> None:
        self._buf += bytes(self.sock.readAll())
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if "event" in msg:
                if msg["event"] == "state":
                    self.stateEvent.emit(msg["data"])
            elif msg.get("id") in self._pending:
                self._pending.pop(msg["id"])(msg)
