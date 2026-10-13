"""Family Connect + clipboard state.

Identity model: the owner is whoever holds ALMANAC_TOKEN. Family members (wife, son) hold their own tokens, issued
by the owner and stored only as SHA-256 hashes. A member token can reach the family space (shared shopping, shared
events, presence) and nothing else: not the owner's personal /state, /sync, the clipboard or Layla's summary.

The clipboard is memory-only on purpose (people copy passwords): a capped ring with a 24h TTL that does not survive a
restart and is never written to disk or logged."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import socket
import sqlite3
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import ws
from .store import FAM_KEY_RE, FAM_TYPES, AlmanacStore, ValidationError

CLIP_MAX = 30
CLIP_TTL_MS = 24 * 3600 * 1000
CLIP_MAX_CHARS = 64 * 1024
MAX_MEMBERS = 8
STATUSES = ("home", "away", "busy", "sleeping", "offline")
_ROLE_OK = re.compile(r"^[A-Za-z][A-Za-z ]{0,19}$")
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

SCHEMA = """
CREATE TABLE IF NOT EXISTS members(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL, token_hash TEXT NOT NULL,
  created_ms INTEGER NOT NULL, seen_ms INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'offline', note TEXT NOT NULL DEFAULT '', revoked INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS hub_meta(k TEXT PRIMARY KEY, v TEXT);
"""


def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _clean(s: Any, n: int) -> str:
    return _CTRL.sub(" ", str(s or "")).strip()[:n]


class Conn:
    """One authenticated WebSocket peer."""

    def __init__(self, sock: socket.socket, role: str, member_id: str):
        self.sock, self.role, self.member_id = sock, role, member_id
        self._lock = threading.Lock()
        self.closed = False

    def send_raw(self, frame: bytes) -> bool:
        with self._lock:
            if self.closed:
                return False
            try:
                self.sock.sendall(frame)
                return True
            except OSError:
                self.closed = True
                return False

    def send(self, obj: Dict[str, Any]) -> bool:
        return self.send_raw(ws.encode_frame(ws.OP_TEXT, json.dumps(obj, ensure_ascii=False).encode()))

    def close(self, code: int = 1000) -> None:
        with self._lock:
            if self.closed:
                return
            self.closed = True
            try:
                self.sock.sendall(ws.close_frame(code))
            except OSError:
                pass
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


class Hub:
    def __init__(self, path: str, clock: Callable[[], float] = time.time, owner_name: str = "Avishkar"):
        self.clock = clock
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.executescript(SCHEMA)
        self._db.commit()
        self.family = AlmanacStore(path, clock, key_re=FAM_KEY_RE, types=FAM_TYPES)
        self._clips: List[Dict[str, Any]] = []
        self._conns: List[Conn] = []
        self._conn_lock = threading.Lock()
        if not self._meta("owner_name"):
            self._set_meta("owner_name", owner_name)

    def _now(self) -> int:
        return int(self.clock() * 1000)

    def _meta(self, k: str) -> str:
        r = self._db.execute("SELECT v FROM hub_meta WHERE k=?", (k,)).fetchone()
        return r[0] if r else ""

    def _set_meta(self, k: str, v: str) -> None:
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO hub_meta(k,v) VALUES(?,?)", (k, v))
            self._db.commit()

    # ---- members -------------------------------------------------------------------------------------------
    def add_member(self, name: str, role: str) -> Tuple[str, str]:
        name, role = _clean(name, 30), _clean(role, 20)
        if not name or not _ROLE_OK.match(role or "Member"):
            raise ValidationError("name and role are required (role: letters only)")
        with self._lock:
            n = self._db.execute("SELECT COUNT(*) FROM members WHERE revoked=0").fetchone()[0]
            if n >= MAX_MEMBERS:
                raise ValidationError("member limit reached")
            mid, token = "m" + secrets.token_hex(4), secrets.token_urlsafe(24)
            self._db.execute("INSERT INTO members(id,name,role,token_hash,created_ms) VALUES(?,?,?,?,?)",
                             (mid, name, role or "Member", _h(token), self._now()))
            self._db.commit()
        return mid, token

    def revoke(self, member_id: str) -> bool:
        with self._lock:
            cur = self._db.execute("UPDATE members SET revoked=1,status='offline' WHERE id=? AND revoked=0", (member_id,))
            self._db.commit()
        if cur.rowcount:
            self.drop_member_conns(member_id)
        return bool(cur.rowcount)

    def auth_member(self, token: str) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        hh = _h(token)
        with self._lock:
            rows = self._db.execute("SELECT id,name,role,token_hash FROM members WHERE revoked=0").fetchall()
        for mid, name, role, th in rows:
            if hmac.compare_digest(hh, th):
                return {"id": mid, "name": name, "role": role}
        return None

    def touch(self, member_id: str) -> None:
        if member_id == "owner":
            self._set_meta("owner_seen", str(self._now()))
            return
        with self._lock:
            self._db.execute("UPDATE members SET seen_ms=? WHERE id=?", (self._now(), member_id))
            self._db.commit()

    def set_presence(self, member_id: str, status: str, note: str = "", name: str = "") -> None:
        if status not in STATUSES:
            raise ValidationError("bad status")
        note = _clean(note, 60)
        if member_id == "owner":
            self._set_meta("owner_status", json.dumps({"status": status, "note": note, "at": self._now()}))
            if name.strip():
                self._set_meta("owner_name", _clean(name, 30))
            return
        with self._lock:
            self._db.execute("UPDATE members SET status=?,note=?,seen_ms=? WHERE id=? AND revoked=0",
                             (status, note, self._now(), member_id))
            self._db.commit()

    def members_public(self) -> List[Dict[str, Any]]:
        raw = self._meta("owner_status")
        os_ = json.loads(raw) if raw else {}
        online = {c.member_id for c in self._snapshot() if not c.closed}
        out = [{"id": "owner", "name": self._meta("owner_name") or "Owner", "role": "Owner",
                "status": os_.get("status", "offline"), "note": os_.get("note", ""),
                "seen": int(self._meta("owner_seen") or 0), "online": "owner" in online}]
        with self._lock:
            rows = self._db.execute(
                "SELECT id,name,role,status,note,seen_ms FROM members WHERE revoked=0 ORDER BY created_ms").fetchall()
        for mid, name, role, status, note, seen in rows:
            out.append({"id": mid, "name": name, "role": role, "status": status, "note": note, "seen": seen,
                        "online": mid in online})
        return out

    # ---- clipboard (memory only) ----------------------------------------------------------------------------
    def clip_add(self, text: Any, device: Any = "") -> Dict[str, Any]:
        if not isinstance(text, str) or not text or len(text) > CLIP_MAX_CHARS:
            raise ValidationError(f"clip text must be 1..{CLIP_MAX_CHARS} characters")
        now = self._now()
        with self._lock:
            self._clips = [c for c in self._clips if now - c["ts"] < CLIP_TTL_MS]
            if self._clips and self._clips[0]["text"] == text:
                self._clips[0]["ts"] = now
                return dict(self._clips[0])
            item = {"id": secrets.token_hex(6), "text": text, "device": _clean(device, 30), "ts": now}
            self._clips.insert(0, item)
            del self._clips[CLIP_MAX:]
            return dict(item)

    def clip_list(self) -> List[Dict[str, Any]]:
        now = self._now()
        with self._lock:
            self._clips = [c for c in self._clips if now - c["ts"] < CLIP_TTL_MS]
            return [dict(c) for c in self._clips]

    def clip_clear(self) -> None:
        with self._lock:
            self._clips = []

    # ---- realtime connections ---------------------------------------------------------------------------------
    def _snapshot(self) -> List[Conn]:
        with self._conn_lock:
            return list(self._conns)

    def register(self, c: Conn) -> bool:
        with self._conn_lock:
            if len(self._conns) >= 50:
                return False
            self._conns.append(c)
            return True

    def unregister(self, c: Conn) -> None:
        with self._conn_lock:
            if c in self._conns:
                self._conns.remove(c)

    def broadcast(self, obj: Dict[str, Any], owner_only: bool = False, skip: Optional[Conn] = None) -> int:
        n = 0
        for c in self._snapshot():
            if c is skip or c.closed or (owner_only and c.role != "owner"):
                continue
            n += 1 if c.send(obj) else 0
        return n

    def drop_member_conns(self, member_id: str) -> None:
        for c in self._snapshot():
            if c.member_id == member_id:
                c.close(4403)
