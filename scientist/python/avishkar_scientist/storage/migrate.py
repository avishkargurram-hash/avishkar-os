"""Apply storage/migrations/*.sql in order, once each, under an advisory
lock so two processes starting together cannot race."""

from __future__ import annotations

from pathlib import Path

from .db import Database

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_LOCK_KEY = 0x5C1E_0001


def migrate(db: Database) -> list:
    applied = []
    with db.tx() as c:
        c.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK_KEY,))
        c.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        done = {r["version"] for r in c.execute("SELECT version FROM schema_migrations").fetchall()}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.stem in done:
                continue
            c.execute(path.read_text(encoding="utf-8"))
            c.execute("INSERT INTO schema_migrations(version) VALUES (%s)", (path.stem,))
            applied.append(path.stem)
    return applied


def reset_for_tests(db: Database) -> None:
    """Drop everything Scientist OS owns. Only ever used on scientist_test."""
    if not db.url.rstrip("/").endswith("_test"):
        raise RuntimeError("refusing to reset a database whose name does not end in _test")
    # Drop tables/sequences, not the schema: the vector extension lives in
    # public and re-creating it needs superuser, which the app role lacks.
    with db.tx() as c:
        for r in c.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'").fetchall():
            c.execute('DROP TABLE IF EXISTS public."%s" CASCADE' % r["tablename"].replace('"', ""))
        for r in c.execute("SELECT sequencename FROM pg_sequences WHERE schemaname='public'").fetchall():
            c.execute('DROP SEQUENCE IF EXISTS public."%s" CASCADE' % r["sequencename"].replace('"', ""))
    migrate(db)
