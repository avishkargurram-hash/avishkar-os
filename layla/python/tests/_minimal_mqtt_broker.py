"""A real, minimal, in-repo MQTT 3.1.1 broker -- a genuine (if
partial) implementation of the real binary wire protocol (CONNECT/
CONNACK, PUBLISH, SUBSCRIBE/SUBACK, PINGREQ/PINGRESP, DISCONNECT,
retained messages, QoS 0 delivery), used only as a test fixture for
`MQTTBridge` (see mqtt/client.py). The same "real local fixture"
discipline `test_smtp_email_transport.py` and
`test_home_assistant_executor.py` established for text protocols,
extended here to a binary one.

Deliberately NOT a production broker: only QoS 0 delivery, no
persistent sessions, no will messages, no packet-identifier tracking
for QoS 1/2. Real enough to prove `MQTTBridge` genuinely speaks MQTT,
not meant to replace a real broker (mosquitto, EMQX, etc.) in
production -- see README.md MQTT section.
"""

from __future__ import annotations

import socket
import struct
import threading
from typing import Dict, List, Optional, Tuple


def _encode_remaining_length(n: int) -> bytes:
    out = bytearray()
    while True:
        byte = n % 128
        n //= 128
        if n > 0:
            byte |= 0x80
        out.append(byte)
        if n == 0:
            break
    return bytes(out)


def _read_remaining_length(read_byte) -> int:
    multiplier = 1
    value = 0
    while True:
        b = read_byte()
        value += (b & 0x7F) * multiplier
        if (b & 0x80) == 0:
            break
        multiplier *= 128
    return value


def _encode_string(s: str) -> bytes:
    data = s.encode("utf-8")
    return struct.pack("!H", len(data)) + data


def _decode_string(data: bytes, offset: int) -> Tuple[str, int]:
    (length,) = struct.unpack_from("!H", data, offset)
    offset += 2
    value = data[offset : offset + length].decode("utf-8")
    return value, offset + length


class _ClientConnection:
    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self.subscriptions: List[str] = []
        self.lock = threading.Lock()

    def send(self, data: bytes) -> None:
        with self.lock:
            self.sock.sendall(data)


class MinimalMQTTBroker:
    def __init__(self, *, host: str = "127.0.0.1", port: int = 0, expected_username: Optional[str] = None, expected_password: Optional[str] = None) -> None:
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((host, port))
        self._server.listen(8)
        self.port = self._server.getsockname()[1]
        self._expected_username = expected_username
        self._expected_password = expected_password
        self._clients: List[_ClientConnection] = []
        self._retained: Dict[str, bytes] = {}
        self._lock = threading.Lock()
        self._running = True
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()
        self.received_publishes: List[Tuple[str, bytes]] = []

    def _accept_loop(self) -> None:
        while self._running:
            try:
                self._server.settimeout(0.5)
                conn, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            client = _ClientConnection(conn)
            with self._lock:
                self._clients.append(client)
            threading.Thread(target=self._handle_client, args=(client,), daemon=True).start()

    def _read_byte(self, sock: socket.socket) -> int:
        b = sock.recv(1)
        if not b:
            raise ConnectionError("connection closed")
        return b[0]

    def _read_exact(self, sock: socket.socket, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("connection closed")
            buf += chunk
        return buf

    def _handle_client(self, client: _ClientConnection) -> None:
        sock = client.sock
        try:
            while self._running:
                try:
                    first_byte = self._read_byte(sock)
                except (ConnectionError, OSError):
                    break
                packet_type = first_byte >> 4
                remaining_length = _read_remaining_length(lambda: self._read_byte(sock))
                body = self._read_exact(sock, remaining_length) if remaining_length else b""

                if packet_type == 1:  # CONNECT
                    self._handle_connect(client, body)
                elif packet_type == 3:  # PUBLISH
                    flags = first_byte & 0x0F
                    self._handle_publish(client, flags, body)
                elif packet_type == 8:  # SUBSCRIBE
                    self._handle_subscribe(client, body)
                elif packet_type == 12:  # PINGREQ
                    client.send(bytes([0xD0, 0x00]))
                elif packet_type == 14:  # DISCONNECT
                    break
                else:
                    break
        except (ConnectionError, OSError):
            pass
        finally:
            with self._lock:
                if client in self._clients:
                    self._clients.remove(client)
            try:
                sock.close()
            except OSError:
                pass

    def _handle_connect(self, client: _ClientConnection, body: bytes) -> None:
        offset = 0
        _protocol_name, offset = _decode_string(body, offset)
        offset += 1  # protocol level byte -- not checked by this minimal fixture
        connect_flags = body[offset]
        offset += 1
        offset += 2  # keep alive
        _client_id, offset = _decode_string(body, offset)

        username_flag = bool(connect_flags & 0x80)
        password_flag = bool(connect_flags & 0x40)
        username = password = None
        if username_flag:
            username, offset = _decode_string(body, offset)
        if password_flag:
            (pw_len,) = struct.unpack_from("!H", body, offset)
            offset += 2
            password = body[offset : offset + pw_len].decode("utf-8")
            offset += pw_len

        return_code = 0
        if self._expected_username is not None:
            if username != self._expected_username or password != self._expected_password:
                return_code = 5  # not authorized

        client.send(bytes([0x20, 0x02, 0x00, return_code]))

    def _handle_publish(self, client: _ClientConnection, flags: int, body: bytes) -> None:
        qos = (flags >> 1) & 0x03
        retain = bool(flags & 0x01)
        offset = 0
        topic, offset = _decode_string(body, offset)
        if qos > 0:
            offset += 2  # packet identifier -- not tracked further (QoS 0 forwarding only)
        payload = body[offset:]

        self.received_publishes.append((topic, payload))
        if retain:
            with self._lock:
                self._retained[topic] = payload

        self.broadcast_to_subscribers(topic, payload)

    def _handle_subscribe(self, client: _ClientConnection, body: bytes) -> None:
        offset = 0
        packet_id = body[offset : offset + 2]
        offset += 2
        granted: List[int] = []
        topic_filters: List[str] = []
        while offset < len(body):
            topic_filter, offset = _decode_string(body, offset)
            offset += 1  # requested QoS byte -- this fixture only ever grants QoS 0
            topic_filters.append(topic_filter)
            granted.append(0)

        with self._lock:
            client.subscriptions.extend(topic_filters)

        suback = bytes([0x90]) + _encode_remaining_length(2 + len(granted)) + packet_id + bytes(granted)
        client.send(suback)

        # Real retained-message delivery on subscribe (MQTT spec
        # behavior): any currently-retained message matching a newly
        # subscribed filter is delivered immediately.
        with self._lock:
            retained_snapshot = dict(self._retained)
        for topic_filter in topic_filters:
            for topic, payload in retained_snapshot.items():
                if self._topic_matches(topic_filter, topic):
                    self._send_publish(client, topic, payload, retain=True)

    @staticmethod
    def _topic_matches(topic_filter: str, topic: str) -> bool:
        filter_levels = topic_filter.split("/")
        topic_levels = topic.split("/")
        for i, level in enumerate(filter_levels):
            if level == "#":
                return True
            if i >= len(topic_levels):
                return False
            if level != "+" and level != topic_levels[i]:
                return False
        return len(filter_levels) == len(topic_levels)

    def _send_publish(self, client: _ClientConnection, topic: str, payload: bytes, *, retain: bool = False) -> None:
        variable_header = _encode_string(topic)
        body = variable_header + payload
        flags = 0x01 if retain else 0x00  # QoS 0 forwarding
        packet = bytes([0x30 | flags]) + _encode_remaining_length(len(body)) + body
        try:
            client.send(packet)
        except OSError:
            pass

    def broadcast_to_subscribers(self, topic: str, payload: bytes) -> None:
        with self._lock:
            targets = [c for c in self._clients if any(self._topic_matches(f, topic) for f in c.subscriptions)]
        for client in targets:
            self._send_publish(client, topic, payload)

    def stop(self) -> None:
        self._running = False
        try:
            self._server.close()
        except OSError:
            pass
