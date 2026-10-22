"""Minimal RFC 6455 server side (stdlib only): handshake accept key, frame encode, incremental frame decode."""

from __future__ import annotations

import base64
import hashlib
import struct
from typing import Optional, Tuple

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
OP_CONT, OP_TEXT, OP_BIN, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA
MAX_PAYLOAD = 256 * 1024


class ProtocolError(Exception):
    def __init__(self, code: int, msg: str = ""):
        super().__init__(msg or str(code))
        self.code = code


def accept_key(client_key: str) -> str:
    return base64.b64encode(hashlib.sha1((client_key.strip() + GUID).encode()).digest()).decode()


def encode_frame(opcode: int, payload: bytes = b"") -> bytes:
    """Server frames are never masked."""
    n = len(payload)
    head = bytes([0x80 | opcode])
    if n < 126:
        head += bytes([n])
    elif n < 65536:
        head += bytes([126]) + struct.pack(">H", n)
    else:
        head += bytes([127]) + struct.pack(">Q", n)
    return head + payload


def close_frame(code: int = 1000) -> bytes:
    return encode_frame(OP_CLOSE, struct.pack(">H", code))


def decode_frame(buf: bytearray) -> Optional[Tuple[bool, int, bytes]]:
    """Pop one complete client frame from buf -> (fin, opcode, payload), or None if more bytes are needed.
    Raises ProtocolError for anything a conforming client would never send."""
    if len(buf) < 2:
        return None
    b0, b1 = buf[0], buf[1]
    if b0 & 0x70:
        raise ProtocolError(1002, "reserved bits set")
    fin, op = bool(b0 & 0x80), b0 & 0x0F
    if not b1 & 0x80:
        raise ProtocolError(1002, "client frames must be masked")
    n, pos = b1 & 0x7F, 2
    if n == 126:
        if len(buf) < 4:
            return None
        n, pos = struct.unpack(">H", bytes(buf[2:4]))[0], 4
    elif n == 127:
        if len(buf) < 10:
            return None
        n, pos = struct.unpack(">Q", bytes(buf[2:10]))[0], 10
    if n > MAX_PAYLOAD:
        raise ProtocolError(1009, "frame too large")
    if op >= 0x8 and (n > 125 or not fin):
        raise ProtocolError(1002, "bad control frame")
    if len(buf) < pos + 4 + n:
        return None
    mask = bytes(buf[pos:pos + 4])
    data = bytes(buf[pos + 4:pos + 4 + n])
    del buf[:pos + 4 + n]
    if n:
        # XOR unmask via big ints: far faster than a Python byte loop for large payloads
        key = (mask * (n // 4 + 1))[:n]
        data = (int.from_bytes(data, "big") ^ int.from_bytes(key, "big")).to_bytes(n, "big")
    return fin, op, data
