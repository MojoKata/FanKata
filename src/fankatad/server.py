"""Unix domain socket server: one reader and one writer thread per client.

Anyone may connect and read state; commands that change anything need polkit
authorization (cached per connection for a few minutes).
"""

from __future__ import annotations

import logging
import os
import queue
import socket
import struct
import threading
import time

from fankata_core import __version__, protocol

from .polkit import Authorizer

log = logging.getLogger("fankatad")
AUTH_TTL = 300.0


class Session:
    """Protocol handling for one client, independent of the transport.

    Transports (Unix socket here, named pipe in server_win) supply pid/uid,
    send() and close(), and feed complete lines to handle_line().
    """
    server: "Server"
    pid: int = 0
    uid: int = -1

    def __init__(self):
        self.subscribed = False
        self.authorized_until = 0.0

    def send(self, msg: dict | bytes, droppable: bool = False) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def handle_line(self, line: bytes) -> None:
        self._handle_line(line)


    def _handle_line(self, line: bytes) -> None:
        try:
            msg = protocol.decode(line)
        except ValueError:
            self.send({"ok": False, "error": "Malformed message."})
            return
        mid = msg.get("id")
        try:
            result = self._dispatch(msg)
            self.send({"id": mid, "ok": True, "result": result})
        except CommandError as e:
            self.send({"id": mid, "ok": False, "error": e.args[0], "errors": e.errors})
        except Exception as e:  # never let one bad request kill the service
            log.exception("command %r failed", msg.get("cmd"))
            self.send({"id": mid, "ok": False, "error": f"Internal error: {e}"})

    def _authorize(self) -> None:
        if time.monotonic() < self.authorized_until:
            return
        ok, why = self.server.auth.check(self.pid, self.uid)
        if not ok:
            raise CommandError(why)
        self.authorized_until = time.monotonic() + AUTH_TTL

    def _dispatch(self, msg: dict):
        cmd = msg.get("cmd")
        ctl = self.server.controller
        if cmd in protocol.WRITE_COMMANDS:
            self._authorize()
        if cmd == "hello":
            return {"version": protocol.VERSION, "service_version": __version__,
                    "compatible": msg.get("version") == protocol.VERSION}
        if cmd == "get_state":
            return ctl.state(include_history=True)
        if cmd == "subscribe":
            self.subscribed = True
            return ctl.state(include_history=True)
        if cmd == "set_config":
            errs = ctl.set_config(msg.get("config") or {})
            if errs:
                raise CommandError(errs[0], errs)
            return ctl.state()
        if cmd == "pulse_start":
            err = ctl.start_pulse(str(msg.get("fan", "")))
            if err:
                raise CommandError(err)
            return ctl.state()
        if cmd == "pulse_stop":
            ctl.stop_pulse()
            return None
        if cmd == "diagnose":
            # Troubleshoot fans (requirement 4.7): what the service sees; Windows adds driver and software facts
            fn = getattr(self.server, "diagnose", None)
            return fn() if fn else {"chips": ctl.hw.chips(), "backend": ctl.hw.describe()}
        if cmd == "service_disable":
            fn = getattr(self.server, "service_disable", None)
            if fn is None:
                raise CommandError("Turning the service off is done with fankata-servicectl on this platform.")
            fn()          # replies first; the service stops a moment later and restores every fan
            return None
        raise CommandError(f"Unknown command “{cmd}”.")


class Client(Session):
    def __init__(self, server: "Server", conn: socket.socket):
        super().__init__()
        self.server = server
        self.conn = conn
        creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        self.pid, self.uid, self.gid = struct.unpack("3i", creds)
        self.out: queue.Queue[bytes | None] = queue.Queue(maxsize=64)
        self.closed = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self._reader, daemon=True, name=f"client-r-{self.pid}").start()
        threading.Thread(target=self._writer, daemon=True, name=f"client-w-{self.pid}").start()

    def send(self, msg: dict | bytes, droppable: bool = False) -> None:
        data = msg if isinstance(msg, bytes) else protocol.encode(msg)
        try:
            self.out.put_nowait(data)
        except queue.Full:
            if droppable:
                return          # slow client: skip a state event rather than block the loop
            self.close()

    def close(self) -> None:
        if self.closed.is_set():
            return
        self.closed.set()
        try:
            self.out.put_nowait(None)
        except queue.Full:
            pass
        try:
            self.conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.server.forget(self)

    def _writer(self) -> None:
        try:
            while True:
                data = self.out.get()
                if data is None or self.closed.is_set():
                    break
                self.conn.sendall(data)
        except OSError:
            pass
        finally:
            self.close()
            self.conn.close()

    def _reader(self) -> None:
        buf = b""
        try:
            while not self.closed.is_set():
                chunk = self.conn.recv(65536)
                if not chunk:
                    break
                buf += chunk
                if len(buf) > protocol.MAX_LINE:
                    break
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if line.strip():
                        self._handle_line(line)
        except OSError:
            pass
        finally:
            self.close()

class CommandError(Exception):
    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or [message]


class Server:
    def __init__(self, path: str, controller, auth: Authorizer):
        self.path = path
        self.controller = controller
        self.auth = auth
        self.clients: set[Client] = set()
        self.lock = threading.Lock()
        self.sock: socket.socket | None = None

    def start(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM | socket.SOCK_CLOEXEC)
        s.bind(self.path)
        os.chmod(self.path, 0o666)     # anyone may connect; writes are authorized per request
        s.listen(16)
        self.sock = s
        threading.Thread(target=self._accept, daemon=True, name="accept").start()
        log.info("listening on %s", self.path)

    def _accept(self) -> None:
        while self.sock:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            try:
                c = Client(self, conn)
            except OSError:
                conn.close()
                continue
            with self.lock:
                self.clients.add(c)
            c.start()

    def forget(self, c: Client) -> None:
        with self.lock:
            self.clients.discard(c)

    def broadcast(self, state: dict) -> None:
        with self.lock:
            targets = [c for c in self.clients if c.subscribed]
        if not targets:
            return
        data = protocol.encode({"event": "state", "data": state})
        for c in targets:
            c.send(data, droppable=True)

    def close(self) -> None:
        s, self.sock = self.sock, None
        if s:
            s.close()
        with self.lock:
            clients = list(self.clients)
        for c in clients:
            c.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass
