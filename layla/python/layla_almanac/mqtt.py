"""Minimal MQTT 3.1.1 client on the standard library (QoS 0 publish/subscribe, keepalive, auto-reconnect).

The Almanac server is stdlib-only by design, and the broker it talks to is the VM-local plaintext listener
(127.0.0.1:51883, never exposed), so this deliberately skips TLS, auth, QoS 1/2 and persistence.
Callbacks run on the reader thread: keep them short and never let them raise.
"""

from __future__ import annotations

import socket
import struct
import threading
import time
from typing import Callable, List, Optional

CONNECT, CONNACK, PUBLISH, SUBSCRIBE, SUBACK, PINGREQ, PINGRESP, DISCONNECT = 1, 2, 3, 8, 9, 12, 13, 14


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b, n = n % 128, n // 128
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _str(s: str) -> bytes:
    b = s.encode()
    return struct.pack("!H", len(b)) + b


def _packet(ptype: int, flags: int, body: bytes) -> bytes:
    return bytes([(ptype << 4) | flags]) + _varint(len(body)) + body


def topic_matches(flt: str, topic: str) -> bool:
    f, t = flt.split("/"), topic.split("/")
    for i, part in enumerate(f):
        if part == "#":
            return True
        if i >= len(t) or (part != "+" and part != t[i]):
            return False
    return len(f) == len(t)


class MqttClient:
    def __init__(self, host: str, port: int, client_id: str, keepalive: int = 30,
                 on_message: Optional[Callable[[str, bytes, bool], None]] = None,
                 on_link: Optional[Callable[[bool], None]] = None):
        self.host, self.port, self.client_id, self.keepalive = host, port, client_id, keepalive
        self.on_message, self.on_link = on_message, on_link
        self._subs: List[str] = []
        self._sock: Optional[socket.socket] = None
        self._wlock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._pid = 0
        self.connected = False

    # ---- public --------------------------------------------------------------------------------------------
    def start(self) -> "MqttClient":
        self._thread = threading.Thread(target=self._loop, name="almanac-mqtt", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        s = self._sock
        if s is not None:
            try:
                s.sendall(_packet(DISCONNECT, 0, b""))
            except OSError:
                pass
            try:
                s.close()
            except OSError:
                pass

    def subscribe(self, flt: str) -> None:
        if flt not in self._subs:
            self._subs.append(flt)
        if self.connected:
            self._send_sub([flt])

    def publish(self, topic: str, payload, retain: bool = False) -> bool:
        if isinstance(payload, str):
            payload = payload.encode()
        return self._write(_packet(PUBLISH, 1 if retain else 0, _str(topic) + bytes(payload)))

    # ---- internals -----------------------------------------------------------------------------------------
    def _write(self, data: bytes, force: bool = False) -> bool:
        s = self._sock
        if s is None or not (self.connected or force):
            return False
        with self._wlock:
            try:
                s.sendall(data)
                return True
            except OSError:
                return False

    def _send_sub(self, flts: List[str], force: bool = False) -> None:
        self._pid = (self._pid % 65535) + 1
        body = struct.pack("!H", self._pid) + b"".join(_str(f) + b"\x00" for f in flts)
        self._write(_packet(SUBSCRIBE, 2, body), force)

    def _set_link(self, up: bool) -> None:
        if self.connected != up:
            self.connected = up
            if self.on_link:
                try:
                    self.on_link(up)
                except Exception:
                    pass

    def _recv_exact(self, s: socket.socket, n: int, mid_packet: bool = True) -> bytes:
        """mid_packet: a read timeout must not abandon a half-read packet (that would desync the stream)."""
        buf = bytearray()
        while len(buf) < n:
            try:
                chunk = s.recv(n - len(buf))
            except socket.timeout:
                if mid_packet or buf:
                    if self._stop.is_set():
                        raise OSError("stopping")
                    continue
                raise
            if not chunk:
                raise OSError("closed")
            buf += chunk
        return bytes(buf)

    def _read_packet(self, s: socket.socket):
        h = self._recv_exact(s, 1, mid_packet=False)[0]
        mult, n = 1, 0
        for _ in range(4):
            b = self._recv_exact(s, 1)[0]
            n += (b & 0x7F) * mult
            if not b & 0x80:
                break
            mult *= 128
        return h >> 4, h & 0x0F, self._recv_exact(s, n) if n else b""

    def _session(self) -> None:
        s = socket.create_connection((self.host, self.port), timeout=10)
        self._sock = s
        body = _str("MQTT") + bytes([4, 0x02]) + struct.pack("!H", self.keepalive) + _str(self.client_id)
        s.sendall(_packet(CONNECT, 0, body))
        ptype, _, payload = self._read_packet(s)
        if ptype != CONNACK or len(payload) < 2 or payload[1] != 0:
            raise OSError("connack refused")
        if self._subs:
            self._send_sub(list(self._subs), force=True)
        self._set_link(True)
        s.settimeout(max(1, self.keepalive / 2))
        last_ping = time.time()
        while not self._stop.is_set():
            try:
                ptype, flags, payload = self._read_packet(s)
            except socket.timeout:
                ptype = None
            if ptype == PUBLISH:
                tl = struct.unpack("!H", payload[:2])[0]
                topic = payload[2:2 + tl].decode("utf-8", "replace")
                off = 2 + tl + (2 if (flags >> 1) & 3 else 0)
                if self.on_message:
                    try:
                        self.on_message(topic, payload[off:], bool(flags & 1))
                    except Exception:
                        pass
            if time.time() - last_ping >= self.keepalive / 2:
                if not self._write(_packet(PINGREQ, 0, b"")):
                    raise OSError("write failed")
                last_ping = time.time()

    def _loop(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                self._session()
                backoff = 1.0
            except Exception:
                pass
            finally:
                self._set_link(False)
                s, self._sock = self._sock, None
                if s is not None:
                    try:
                        s.close()
                    except OSError:
                        pass
            if self._stop.wait(backoff):
                return
            backoff = min(backoff * 2, 15.0)
