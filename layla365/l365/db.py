import psycopg2
import psycopg2.extras

from . import config


def connect(role_name: str):
    """Connect as l365_<role_name>. Agents use their own role, so Postgres
    privileges and row-level security enforce isolation, not just our code."""
    conn = psycopg2.connect(
        host=config.PG_HOST, port=config.PG_PORT, dbname=config.PG_DB,
        user=f"l365_{role_name}", password=config.pg_password(role_name),
        connect_timeout=5, application_name=f"l365-{role_name}",
    )
    conn.autocommit = True
    return conn


def Json(obj):
    return psycopg2.extras.Json(obj)
