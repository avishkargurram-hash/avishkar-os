"""Per-record last-write-wins store. The app flattens its DB into keyed records
(ev:<id>, rem:<id>, well:<id>, note:<id>, rm:<id>, rd:<date>, ro:<date>, wd:<date>, goal);
each carries an update time `u` (ms). A null value is a tombstone (deleted record)."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

SCHEMA = """
CREATE TABLE IF NOT EXISTS records(
  key TEXT PRIMARY KEY, u INTEGER NOT NULL, rev INTEGER NOT NULL, val TEXT);
CREATE INDEX IF NOT EXISTS records_rev ON records(rev);
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
"""

_ID = r"[A-Za-z0-9_-]{1,40}"
_DATE = r"\d{4}-\d{2}-\d{2}"
# Plain modules: prj projects, chk checklists, shop shopping, exp expenses, alm alarms.
# Zero-knowledge vaults: vh health, vd documents, vp passwords (opaque ciphertext) + vmeta (salt + verifier).
KEY_RE = re.compile(rf"^(?:(?:ev|rem|well|note|rm|prj|chk|shop|exp|alm|vh|vd|vp):{_ID}|(?:rd|ro|wd):{_DATE}|goal|vmeta)$")
FAM_KEY_RE = re.compile(rf"^(?:fshop|fev):{_ID}$")
MAX_VALUE_BYTES = 512 * 1024
MAX_RECORDS_PER_PUSH = 5000
FUTURE_SKEW_MS = 5 * 60 * 1000
TOMBSTONE_KEEP_MS = 180 * 86400 * 1000
_TYPES = {"ev": dict, "rem": dict, "well": dict, "note": dict, "rm": dict, "rd": dict, "wd": dict, "ro": list,
          "prj": dict, "chk": dict, "shop": dict, "exp": dict, "alm": dict, "vh": dict, "vd": dict, "vp": dict}
FAM_TYPES = {"fshop": dict, "fev": dict}
_CIPHER = {"vh", "vd", "vp"}
_B64 = re.compile(r"^[A-Za-z0-9+/_=-]*$")


class ValidationError(ValueError):
    pass


def _check_cipher(val: dict) -> None:
    """Vault records are opaque to the server, but must at least look like ciphertext so plaintext cannot
    be stored here by a buggy client."""
    iv, ct = val.get("iv"), val.get("ct")
    if val.get("v") != 1 or not isinstance(iv, str) or not isinstance(ct, str) or not iv or not ct:
        raise ValidationError("vault record must be {v:1, iv, ct}")
    if len(iv) > 64 or not _B64.match(iv) or not _B64.match(ct):
        raise ValidationError("vault record must be base64 ciphertext")
    if set(val) - {"v", "iv", "ct", "t"}:
        raise ValidationError("vault record has unexpected fields")


def _check_vmeta(val: Any) -> None:
    if (not isinstance(val, dict) or not isinstance(val.get("salt"), str) or not isinstance(val.get("ver"), str)
            or not isinstance(val.get("iter"), int) or isinstance(val.get("iter"), bool)
            or not 100_000 <= val["iter"] <= 5_000_000 or len(val["salt"]) > 64 or len(val["ver"]) > 256
            or not _B64.match(val["salt"]) or not _B64.match(val["ver"])):
        raise ValidationError("bad vault meta")


def _check_value(key: str, val: Any, types: Optional[Dict[str, type]] = None) -> str:
    types = types or _TYPES
    prefix = key.split(":", 1)[0]
    if key == "goal":
        if isinstance(val, bool) or not isinstance(val, int) or not 1 <= val <= 100000:
            raise ValidationError("goal must be an int 1..100000")
    elif key == "vmeta":
        _check_vmeta(val)
    elif not isinstance(val, types[prefix]):
        raise ValidationError(f"bad value type for {prefix}")
    elif prefix in _CIPHER:
        _check_cipher(val)
    raw = json.dumps(val, separators=(",", ":"), ensure_ascii=False)
    if len(raw.encode()) > MAX_VALUE_BYTES:
        raise ValidationError("record too large")
    return raw


def _check_u(u: Any, now_ms: int) -> int:
    if isinstance(u, bool) or not isinstance(u, (int, float)) or u < 0:
        raise ValidationError("bad timestamp")
    return min(int(u), now_ms + FUTURE_SKEW_MS)


def clean_templates(t: Any) -> Optional[dict]:
    if not isinstance(t, dict):
        return None
    out = {}
    for name in ("default", "monday"):
        blocks = t.get(name)
        if not isinstance(blocks, list) or len(blocks) > 60:
            return None
        out[name] = [{k: str(b.get(k, ""))[:200] for k in ("id", "time", "title", "desc")}
                     for b in blocks if isinstance(b, dict) and b.get("id")]
    return out


class AlmanacStore:
    def __init__(self, path: str, clock: Callable[[], float] = time.time,
                 key_re: "re.Pattern[str]" = KEY_RE, types: Optional[Dict[str, type]] = None):
        self.clock = clock
        self.key_re = key_re
        self.types = types or _TYPES
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.executescript(SCHEMA)
        self._db.commit()

    def _now_ms(self) -> int:
        return int(self.clock() * 1000)

    def _meta(self, k: str, default: str = "") -> str:
        r = self._db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return r[0] if r else default

    def _set_meta(self, k: str, v: str) -> None:
        self._db.execute("INSERT OR REPLACE INTO meta(k,v) VALUES(?,?)", (k, v))

    def merge(self, records: Dict[str, Any], tombstones: Dict[str, Any], templates: Any = None,
              device: str = "") -> int:
        """Validate everything first, then apply atomically. Returns the number of records applied."""
        now = self._now_ms()
        if len(records) + len(tombstones) > MAX_RECORDS_PER_PUSH:
            raise ValidationError("too many records")
        todo: list = []
        for key, rec in records.items():
            if not isinstance(key, str) or not self.key_re.match(key) or not isinstance(rec, dict) or "v" not in rec:
                raise ValidationError(f"bad record {str(key)[:40]!r}")
            todo.append((key, _check_u(rec.get("u"), now), _check_value(key, rec["v"], self.types)))
        for key, u in tombstones.items():
            if not isinstance(key, str) or not self.key_re.match(key):
                raise ValidationError(f"bad tombstone {str(key)[:40]!r}")
            todo.append((key, _check_u(u, now), None))
        tpl = clean_templates(templates) if templates is not None else None
        applied = 0
        with self._lock:
            rev = int(self._meta("rev", "0"))
            for key, u, val in todo:
                cur = self._db.execute("SELECT u FROM records WHERE key=?", (key,)).fetchone()
                if cur is not None and cur[0] >= u:
                    continue
                rev += 1
                applied += 1
                self._db.execute("INSERT OR REPLACE INTO records(key,u,rev,val) VALUES(?,?,?,?)", (key, u, rev, val))
            self._db.execute("DELETE FROM records WHERE val IS NULL AND u<?", (now - TOMBSTONE_KEEP_MS,))
            self._set_meta("rev", str(rev))
            self._set_meta("last_sync_ms", str(now))
            if device:
                self._set_meta("device", device[:40])
            if tpl is not None:
                self._set_meta("templates", json.dumps(tpl))
            self._db.commit()
        return applied

    def changes_since(self, since: int = 0) -> Tuple[Dict[str, Any], Dict[str, int], int]:
        with self._lock:
            rows = self._db.execute("SELECT key,u,val FROM records WHERE rev>? ORDER BY rev", (since,)).fetchall()
            rev = int(self._meta("rev", "0"))
        recs, tombs = {}, {}
        for key, u, val in rows:
            if val is None:
                tombs[key] = u
            else:
                recs[key] = {"u": u, "v": json.loads(val)}
        return recs, tombs, rev

    def all_records(self, prefix: str) -> Dict[str, Any]:
        with self._lock:
            rows = self._db.execute("SELECT key,val FROM records WHERE key LIKE ? AND val IS NOT NULL",
                                    (prefix + "%",)).fetchall()
        return {k: json.loads(v) for k, v in rows}

    def get(self, key: str) -> Any:
        with self._lock:
            r = self._db.execute("SELECT val FROM records WHERE key=? AND val IS NOT NULL", (key,)).fetchone()
        return json.loads(r[0]) if r else None

    def templates(self) -> Optional[dict]:
        with self._lock:
            raw = self._meta("templates")
        return json.loads(raw) if raw else None

    def last_sync_ms(self) -> int:
        with self._lock:
            return int(self._meta("last_sync_ms", "0"))
