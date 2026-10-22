"""Thin psycopg3 access layer.

Everything durable goes through `Database.tx()` -- one transaction per
logical step, so a crash between steps never leaves half-written state.
A small pool is used when psycopg_pool is installed; otherwise each
transaction opens its own connection (fine for tests and low volume).
"""

from __future__ import annotations

import contextlib
import json
import threading
from typing import Any, Iterator, Optional

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

try:  # optional
    from psycopg_pool import ConnectionPool
except Exception:  # pragma: no cover
    ConnectionPool = None


def J(value: Any) -> Jsonb:
    """Wrap a Python value for a jsonb parameter."""
    return Jsonb(value, dumps=lambda v: json.dumps(v, default=str))


class Database:
    def __init__(self, url: str, *, min_size: int = 1, max_size: int = 6):
        self.url = url
        self._pool = None
        self._lock = threading.Lock()
        if ConnectionPool is not None:
            self._pool = ConnectionPool(
                url, min_size=min_size, max_size=max_size, open=True,
                kwargs={"row_factory": dict_row, "autocommit": False},
            )

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()

    @contextlib.contextmanager
    def tx(self) -> Iterator[psycopg.Connection]:
        if self._pool is not None:
            with self._pool.connection() as conn:
                with conn.transaction():
                    yield conn
            return
        conn = psycopg.connect(self.url, row_factory=dict_row)
        try:
            with conn.transaction():
                yield conn
        finally:
            conn.close()

    def connect_autocommit(self) -> psycopg.Connection:
        """Dedicated connection for LISTEN (SSE) -- caller closes it."""
        return psycopg.connect(self.url, row_factory=dict_row, autocommit=True)

    # convenience helpers -------------------------------------------------
    def one(self, sql: str, params: Any = None) -> Optional[dict]:
        with self.tx() as c:
            return c.execute(sql, params).fetchone()

    def all(self, sql: str, params: Any = None) -> list:
        with self.tx() as c:
            return c.execute(sql, params).fetchall()

    def run(self, sql: str, params: Any = None) -> int:
        with self.tx() as c:
            return c.execute(sql, params).rowcount
