"""SQLiteMemoryPolicy -- a single (kind, key, value) table via stdlib
sqlite3. Implements avishkar_agent.MemoryPolicy verbatim.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

from avishkar_agent import MemoryPolicy

from ..errors import InvalidMemoryKindError

_KINDS = ("short_term", "long_term", "episodic", "semantic")


class SQLiteMemoryPolicy(MemoryPolicy):
    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path)
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
        self._conn.execute(
            "INSERT INTO memory (kind, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT(kind, key) DO UPDATE SET value = excluded.value",
            (kind, key, json.dumps(value)),
        )
        self._conn.commit()

    def recall(self, kind: str, key: str) -> Optional[Any]:
        self._check_kind(kind)
        row = self._conn.execute(
            "SELECT value FROM memory WHERE kind = ? AND key = ?", (kind, key)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def forget(self, kind: str, key: str) -> None:
        self._check_kind(kind)
        self._conn.execute("DELETE FROM memory WHERE kind = ? AND key = ?", (kind, key))
        self._conn.commit()

    def list_keys(self, kind: str) -> tuple:
        self._check_kind(kind)
        rows = self._conn.execute("SELECT key FROM memory WHERE kind = ?", (kind,)).fetchall()
        return tuple(row[0] for row in rows)

    def close(self) -> None:
        self._conn.close()
