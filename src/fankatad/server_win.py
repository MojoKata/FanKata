"""Windows transport: a named pipe (\\\\.\\pipe\\fankata) carrying the same protocol.

Overlapped I/O so a client's reads and writes don't block each other. The pipe's
security descriptor lets SYSTEM and Administrators do anything and any
authenticated user connect; changes are then authorized per request by
WinAuthorizer (the Windows counterpart of the polkit rule, requirement 1.8).
"""

from __future__ import annotations

import logging
import queue
import threading

import pywintypes
import win32api
import win32event
import win32file
import win32pipe
import win32security
import win32ts
import winerror

from fankata_core import protocol

from .server import CommandError, Session  # noqa: F401

log = logging.getLogger("fankatad")
PIPE_REJECT_REMOTE_CLIENTS = 0x00000008
FILE_FLAG_FIRST_PIPE_INSTANCE = 0x00080000        # not exported by pywin32
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008
SDDL = "D:P(A;;GA;;;SY)(A;;GA;;;BA)(A;;GRGW;;;AU)"


class WinAuthorizer:
    """Allow changes from an elevated administrator (or SYSTEM), or from a user in an
    active interactive session at this PC — like polkit's allow_active."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def check(self, pid: int, uid: int) -> tuple[bool, str]:
        if not self.enabled:
            return True, ""
        try:
            if _elevated(pid):
                return True, ""
            sid = win32ts.ProcessIdToSessionId(pid)
            for s in win32ts.WTSEnumerateSessions(win32ts.WTS_CURRENT_SERVER_HANDLE):
                if s["SessionId"] == sid and s["State"] == win32ts.WTSActive:
                    return True, ""
        except pywintypes.error as e:
            log.info("authorization check for pid %s failed: %s", pid, e)
        return False, "Only someone signed in at this PC, or an administrator, can change fan control."


def _elevated(pid: int) -> bool:
    hp = win32api.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    try:
        ht = win32security.OpenProcessToken(hp, TOKEN_QUERY)
        try:
            return bool(win32security.GetTokenInformation(ht, win32security.TokenElevation))
        finally:
            ht.Close()
    finally:
        hp.Close()


def _event():
    return win32event.CreateEvent(None, True, False, None)


class PipeClient(Session):
    def __init__(self, server: "PipeServer", handle):
        super().__init__()
        self.server = server
        self.h = handle
        self.pid = win32pipe.GetNamedPipeClientProcessId(handle)
        self.uid = -1
        self.out: queue.Queue[bytes | None] = queue.Queue(maxsize=64)
        self.closed = threading.Event()
        self._writer_done = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self._reader, daemon=True, name=f"pipe-r-{self.pid}").start()
        threading.Thread(target=self._writer, daemon=True, name=f"pipe-w-{self.pid}").start()

    def send(self, msg, droppable=False):
        data = msg if isinstance(msg, bytes) else protocol.encode(msg)
        try:
            self.out.put_nowait(data)
        except queue.Full:
            if not droppable:
                self.close()

    def close(self):
        if self.closed.is_set():
            return
        self.closed.set()
        try:
            self.out.put_nowait(None)
        except queue.Full:
            pass
        try:
            win32pipe.DisconnectNamedPipe(self.h)     # wakes a pending read with an error
        except pywintypes.error:
            pass
        self.server.forget(self)

    def _writer(self):
        ov = pywintypes.OVERLAPPED()
        ov.hEvent = _event()
        try:
            while True:
                data = self.out.get()
                if data is None or self.closed.is_set():
                    break
                win32file.WriteFile(self.h, data, ov)
                win32file.GetOverlappedResult(self.h, ov, True)
        except pywintypes.error:
            pass
        finally:
            self._writer_done.set()
            self.close()

    def _reader(self):
        ov = pywintypes.OVERLAPPED()
        ov.hEvent = _event()
        buf = win32file.AllocateReadBuffer(65536)
        pending = b""
        try:
            while not self.closed.is_set():
                try:
                    win32file.ReadFile(self.h, buf, ov)
                    n = win32file.GetOverlappedResult(self.h, ov, True)
                except pywintypes.error as e:
                    if e.winerror == winerror.ERROR_MORE_DATA:
                        n = len(buf)
                    else:
                        break
                if n == 0:
                    break
                pending += bytes(buf[:n])
                if len(pending) > protocol.MAX_LINE:
                    break
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    if line.strip():
                        self.handle_line(line)
        finally:
            self.close()
            self._writer_done.wait(2)
            try:
                win32file.CloseHandle(self.h)
            except pywintypes.error:
                pass


class PipeServer:
    def __init__(self, path: str, controller, auth: WinAuthorizer):
        self.path = path
        self.controller = controller
        self.auth = auth
        self.clients: set[PipeClient] = set()
        self.lock = threading.Lock()
        self._stop = _event()
        self._running = False
        sd = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(SDDL, win32security.SDDL_REVISION_1)
        self._sa = win32security.SECURITY_ATTRIBUTES()
        self._sa.SECURITY_DESCRIPTOR = sd

    def _instance(self, first: bool):
        flags = win32pipe.PIPE_ACCESS_DUPLEX | win32file.FILE_FLAG_OVERLAPPED
        if first:
            flags |= FILE_FLAG_FIRST_PIPE_INSTANCE      # refuse to start if someone squats the name
        return win32pipe.CreateNamedPipe(
            self.path, flags,
            win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
            win32pipe.PIPE_UNLIMITED_INSTANCES, 65536, 65536, 0, self._sa)

    def start(self) -> None:
        first = self._instance(True)
        self._running = True
        threading.Thread(target=self._accept, args=(first,), daemon=True, name="pipe-accept").start()
        log.info("listening on %s", self.path)

    def _accept(self, h) -> None:
        while self._running:
            ov = pywintypes.OVERLAPPED()
            ov.hEvent = _event()
            try:
                rc = win32pipe.ConnectNamedPipe(h, ov)
            except pywintypes.error as e:
                rc = e.winerror
            if rc == winerror.ERROR_IO_PENDING:
                which = win32event.WaitForMultipleObjects([ov.hEvent, self._stop], False, win32event.INFINITE)
                if which != win32event.WAIT_OBJECT_0:
                    win32file.CloseHandle(h)
                    return
            elif rc not in (0, winerror.ERROR_PIPE_CONNECTED):
                log.warning("ConnectNamedPipe failed: %s", rc)
                win32file.CloseHandle(h)
                h = self._instance(False)
                continue
            try:
                c = PipeClient(self, h)
                with self.lock:
                    self.clients.add(c)
                c.start()
            except pywintypes.error as e:
                log.warning("client setup failed: %s", e)
                win32file.CloseHandle(h)
            h = self._instance(False)

    def forget(self, c) -> None:
        with self.lock:
            self.clients.discard(c)

    def broadcast(self, state: dict) -> None:
        with self.lock:
            targets = [c for c in self.clients if c.subscribed]
        if targets:
            data = protocol.encode({"event": "state", "data": state})
            for c in targets:
                c.send(data, droppable=True)

    def close(self) -> None:
        self._running = False
        win32event.SetEvent(self._stop)
        with self.lock:
            clients = list(self.clients)
        for c in clients:
            c.close()
