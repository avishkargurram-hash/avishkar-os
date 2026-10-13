"""SQLiteMemoryPolicy -- a single (kind, key, value) table via stdlib
sqlite3. Implements avishkar_agent.MemoryPolicy verbatim.

Concurrency (Priority 17.4 platform-wide hardening pass, ADR-0024):
`sqlite3.connect()` defaults to `check_same_thread=True`, which raises
if the connection is ever used from a thread other than the one that
created it -- meaning this backend, as originally written, could not
be used by a multi-threaded caller (e.g. ExecutiveRuntime driven by a
thread pool) at all, not even safely-if-slowly. `check_same_thread=
False` plus a lock around every method makes it actually usable
cross-thread: each individual statement here is already atomic at the
SQL level (a single INSERT...ON CONFLICT, not a separate SELECT-then-
INSERT), so the lock's job is purely to serialize access to the one
shared connection object, not to fix a read-modify-write race the way
FileMemoryPolicy's lock does. A narrow, additive exception to
memory-factory's Phase 5 "locked" status -- justified because the
Phase 17 directive explicitly names Memory as an audit/harden target;
every existing test still passes unmodified.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any, Optional

from avishkar_agent import MemoryPolicy

from ..errors import InvalidMemoryKindError

_KINDS = ("short_term", "long_term", "episodic", "semantic")


class SQLiteMemoryPolicy(MemoryPolicy):
    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS memory ("
                "kind TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, "
                "PRIMARY KEY (kind, key))"
            )
            self._conn.commit()

    def _check_kind(self, kind: str) -> None:
        if kind not in _KINDS:
            raise InvalidMemoryKindError(f"Unknown memory kind '{kind}' -- expected one of {_KINDS}")

    def remember(self, kind: str, key: str, value: Any) -> None:
        self._check_kind(kind)
        with self._lock:
            self._conn.execute(
                "INSERT INTO memory (kind, key, value) VALUES (?, ?, ?) "
                "ON CONFLICT(kind, key) DO UPDATE SET value = excluded.value",
                (kind, key, json.dumps(value)),
            )
            self._conn.commit()

    def recall(self, kind: str, key: str) -> Optional[Any]:
        self._check_kind(kind)
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM memory WHERE kind = ? AND key = ?", (kind, key)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def forget(self, kind: str, key: str) -> None:
        self._check_kind(kind)
        with self._lock:
            self._conn.execute("DELETE FROM memory WHERE kind = ? AND key = ?", (kind, key))
            self._conn.commit()

    def list_keys(self, kind: str) -> tuple:
        self._check_kind(kind)
        with self._lock:
            rows = self._conn.execute("SELECT key FROM memory WHERE kind = ?", (kind,)).fetchall()
        return tuple(row[0] for row in rows)

    def close(self) -> None:
        with self._lock:
            self._conn.close()
