"""Persisted mission events (spec section 15). Every event is a row in
`events` (the replayable log) plus a NOTIFY so live SSE streams wake
immediately instead of polling."""

from __future__ import annotations

import json
from typing import Optional

from .storage.db import J

EVENT_TYPES = frozenset({
    "MISSION_CREATED", "MISSION_STARTED", "MISSION_PAUSED", "MISSION_RESUMED", "MISSION_CANCELLED",
    "TASK_CREATED", "TASK_STARTED", "TASK_COMPLETED", "TASK_FAILED",
    "SOURCE_FOUND", "SOURCE_ANALYZED", "CLAIM_CREATED", "EVIDENCE_ADDED", "CONTRADICTION_FOUND",
    "HYPOTHESIS_CREATED", "HYPOTHESIS_UPDATED",
    "EXPERIMENT_CREATED", "EXPERIMENT_STARTED", "EXPERIMENT_COMPLETED",
    "REPLICATION_STARTED", "REPLICATION_COMPLETED", "CRITIQUE_COMPLETED",
    "STATE_UPDATED", "PHASE_CHANGED", "BUDGET_WARNING", "TERMINATION_CHECK",
    "VERDICT_STARTED", "VERDICT_READY", "REPORT_READY", "MISSION_COMPLETED", "MISSION_FAILED",
    "APPROVAL_REQUESTED", "MODEL_ESCALATED",
})

CHANNEL = "sci_events"


def emit(conn, mission_id: str, type_: str, payload: Optional[dict] = None) -> int:
    """Insert + NOTIFY inside the caller's transaction, so an event is only
    visible if the state change it describes committed."""
    if type_ not in EVENT_TYPES:
        raise ValueError(f"unknown event type {type_}")
    row = conn.execute(
        "INSERT INTO events(mission_id, type, payload) VALUES (%s,%s,%s) RETURNING id",
        (mission_id, type_, J(payload or {})),
    ).fetchone()
    conn.execute("SELECT pg_notify(%s, %s)", (CHANNEL, json.dumps({"m": mission_id, "id": row["id"]})))
    return row["id"]


def list_events(db, mission_id: str, after_id: int = 0, limit: int = 500) -> list:
    return db.all(
        "SELECT id, type, payload, created_at FROM events WHERE mission_id=%s AND id>%s ORDER BY id LIMIT %s",
        (mission_id, after_id, limit),
    )


def to_sse(ev: dict) -> str:
    data = json.dumps({"id": ev["id"], "type": ev["type"], "payload": ev["payload"],
                       "at": ev["created_at"].isoformat() if hasattr(ev["created_at"], "isoformat") else str(ev["created_at"])},
                      default=str)
    return f"id: {ev['id']}\nevent: {ev['type']}\ndata: {data}\n\n"
