"""WorkflowEngine (spec sections 4, 12, 13, 41).

ADR-0046 decision 1: the durable engine is Postgres itself. Tasks are rows;
leasing is `FOR UPDATE SKIP LOCKED`; a lease has an owner and an expiry,
so a crashed worker's tasks are re-leased after `lease_expires_at`
(at-least-once). Completion is *fenced* by lease_owner, so a zombie worker
that wakes after its lease was stolen cannot overwrite the new owner's
result. Handlers are written idempotently (unique keys + ON CONFLICT), so
re-execution after a crash is safe.

`WorkflowEngine` is the interface; `TemporalAdapter` (temporal_adapter.py)
documents how the same contract maps onto Temporal if we outgrow Postgres.
"""

from __future__ import annotations

import abc
import dataclasses
import hashlib
import json
from typing import Iterable, Optional, Sequence

from ..domain import TERMINAL_TASK, TaskStatus
from ..events import emit
from ..storage.db import Database, J


@dataclasses.dataclass
class TaskSpec:
    type: str
    queue: str
    input: dict
    priority: int = 5
    dedupe_key: Optional[str] = None
    depends_on: Sequence[int] = ()
    iteration: int = 0
    max_attempts: int = 3
    backoff_s: float = 5.0
    model_requirement: Optional[str] = None
    tool_requirement: Optional[str] = None
    estimated_cost: float = 0.0
    estimated_duration: float = 0.0
    delay_s: float = 0.0              # earliest start = now + delay_s
    counts_toward_budget: bool = True  # reconciler ticks are bookkeeping, not research work

    def key(self) -> str:
        if self.dedupe_key:
            return self.dedupe_key
        h = hashlib.sha256(json.dumps(self.input, sort_keys=True, default=str).encode()).hexdigest()[:16]
        return f"{self.type}:{self.iteration}:{h}"


class WorkflowEngine(abc.ABC):
    @abc.abstractmethod
    def enqueue(self, conn, mission_id: str, spec: TaskSpec) -> Optional[int]: ...

    @abc.abstractmethod
    def lease(self, worker: str, queues: Iterable[str], lease_s: int, limit: int = 1) -> list: ...

    @abc.abstractmethod
    def heartbeat(self, task_id: int, worker: str, lease_s: int) -> bool: ...

    @abc.abstractmethod
    def complete(self, task_id: int, worker: str, output: dict, spawn: Sequence[TaskSpec] = ()) -> bool: ...

    @abc.abstractmethod
    def fail(self, task_id: int, worker: str, error: str, retryable: bool = True) -> str: ...

    @abc.abstractmethod
    def recover_stale(self) -> int: ...

    @abc.abstractmethod
    def cancel_mission(self, conn, mission_id: str) -> int: ...


_LEASE_SQL = """
WITH ready AS (
  SELECT t.id
    FROM tasks t
    JOIN missions m ON m.id = t.mission_id
   WHERE t.status = 'PENDING'
     AND t.queue = ANY(%(queues)s)
     AND t.available_at <= now()
     AND m.paused = false
     AND m.cancel_requested = false
     AND m.status NOT IN ('COMPLETED','FAILED','CANCELLED','PAUSED','WAITING_FOR_HUMAN')
     AND NOT EXISTS (
           SELECT 1 FROM tasks d
            WHERE d.id = ANY(t.depends_on)
              AND d.status NOT IN ('SUCCEEDED','DEAD','CANCELLED'))
   ORDER BY m.priority DESC, t.priority DESC, t.created_at, t.id
   LIMIT %(limit)s
   FOR UPDATE OF t SKIP LOCKED
)
UPDATE tasks t
   SET status = 'LEASED',
       lease_owner = %(worker)s,
       lease_expires_at = now() + make_interval(secs => %(lease_s)s),
       attempts = t.attempts + 1,
       started_at = COALESCE(t.started_at, now())
  FROM ready
 WHERE t.id = ready.id
RETURNING t.*
"""


class PgWorkflowEngine(WorkflowEngine):
    def __init__(self, db: Database):
        self.db = db

    # -- producing ----------------------------------------------------------
    def enqueue(self, conn, mission_id: str, spec: TaskSpec) -> Optional[int]:
        row = conn.execute(
            """INSERT INTO tasks(mission_id, type, queue, priority, iteration, dedupe_key, depends_on,
                                 input, model_requirement, tool_requirement, estimated_cost,
                                 estimated_duration, retry_policy, max_attempts, available_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now() + make_interval(secs => %s))
               ON CONFLICT (mission_id, dedupe_key) DO NOTHING
               RETURNING id""",
            (mission_id, spec.type, spec.queue, spec.priority, spec.iteration, spec.key(),
             list(spec.depends_on), J(spec.input), spec.model_requirement, spec.tool_requirement,
             spec.estimated_cost, spec.estimated_duration,
             J({"max_attempts": spec.max_attempts, "backoff_s": spec.backoff_s}), spec.max_attempts,
             float(spec.delay_s)),
        ).fetchone()
        if row is None:
            return None
        if spec.counts_toward_budget:
            conn.execute(
                "INSERT INTO budgets(mission_id, tasks_used) VALUES (%s,1) "
                "ON CONFLICT (mission_id) DO UPDATE SET tasks_used = budgets.tasks_used + 1, updated_at=now()",
                (mission_id,),
            )
        emit(conn, mission_id, "TASK_CREATED", {"task_id": row["id"], "type": spec.type, "queue": spec.queue})
        return row["id"]

    # -- consuming ----------------------------------------------------------
    def lease(self, worker: str, queues: Iterable[str], lease_s: int, limit: int = 1) -> list:
        with self.db.tx() as c:
            rows = c.execute(_LEASE_SQL, {"queues": list(queues), "limit": limit,
                                          "worker": worker, "lease_s": lease_s}).fetchall()
            for r in rows:
                emit(c, r["mission_id"], "TASK_STARTED",
                     {"task_id": r["id"], "type": r["type"], "attempt": r["attempts"]})
            return rows

    def heartbeat(self, task_id: int, worker: str, lease_s: int) -> bool:
        with self.db.tx() as c:
            n = c.execute(
                "UPDATE tasks SET lease_expires_at = now() + make_interval(secs => %s) "
                "WHERE id=%s AND status='LEASED' AND lease_owner=%s",
                (lease_s, task_id, worker),
            ).rowcount
            return n == 1

    def checkpoint(self, task_id: int, worker: str, data: dict) -> bool:
        with self.db.tx() as c:
            return c.execute(
                "UPDATE tasks SET checkpoint=%s WHERE id=%s AND status='LEASED' AND lease_owner=%s",
                (J(data), task_id, worker),
            ).rowcount == 1

    def complete(self, task_id: int, worker: str, output: dict, spawn: Sequence[TaskSpec] = ()) -> bool:
        with self.db.tx() as c:
            row = c.execute(
                "UPDATE tasks SET status='SUCCEEDED', output=%s, finished_at=now(), lease_owner=NULL, "
                "lease_expires_at=NULL, last_error=NULL "
                "WHERE id=%s AND status='LEASED' AND lease_owner=%s RETURNING mission_id, type, attempts, started_at, iteration",
                (J(output), task_id, worker),
            ).fetchone()
            if row is None:   # lease lost -> another worker owns it now; drop our result
                return False
            c.execute("INSERT INTO task_attempts(task_id, attempt, worker, status, started_at) "
                      "VALUES (%s,%s,%s,'SUCCEEDED',%s)", (task_id, row["attempts"], worker, row["started_at"]))
            for s in spawn:
                if not s.iteration:
                    s.iteration = row["iteration"]
                self.enqueue(c, row["mission_id"], s)
            emit(c, row["mission_id"], "TASK_COMPLETED", {"task_id": task_id, "type": row["type"]})
            return True

    def fail(self, task_id: int, worker: str, error: str, retryable: bool = True) -> str:
        error = (error or "")[:2000]
        with self.db.tx() as c:
            row = c.execute(
                "SELECT mission_id, type, attempts, max_attempts, retry_policy, started_at FROM tasks "
                "WHERE id=%s AND status='LEASED' AND lease_owner=%s FOR UPDATE",
                (task_id, worker),
            ).fetchone()
            if row is None:
                return "LEASE_LOST"
            dead = (not retryable) or row["attempts"] >= row["max_attempts"]
            backoff = float((row["retry_policy"] or {}).get("backoff_s", 5)) * (2 ** max(0, row["attempts"] - 1))
            new_status = TaskStatus.DEAD if dead else TaskStatus.PENDING
            c.execute(
                "UPDATE tasks SET status=%s, last_error=%s, lease_owner=NULL, lease_expires_at=NULL, "
                "available_at = now() + make_interval(secs => %s), finished_at = CASE WHEN %s THEN now() END "
                "WHERE id=%s",
                (str(new_status), error, 0 if dead else min(backoff, 600), dead, task_id),
            )
            c.execute("INSERT INTO task_attempts(task_id, attempt, worker, status, error, started_at) "
                      "VALUES (%s,%s,%s,'FAILED',%s,%s)", (task_id, row["attempts"], worker, error, row["started_at"]))
            emit(c, row["mission_id"], "TASK_FAILED",
                 {"task_id": task_id, "type": row["type"], "error": error[:300], "dead_lettered": dead})
            return str(new_status)

    def recover_stale(self) -> int:
        """Expired leases: back to PENDING (or DEAD if attempts exhausted)."""
        with self.db.tx() as c:
            rows = c.execute(
                """UPDATE tasks SET
                       status = CASE WHEN attempts >= max_attempts THEN 'DEAD' ELSE 'PENDING' END,
                       last_error = 'lease expired (worker crashed or stalled)',
                       lease_owner = NULL, lease_expires_at = NULL,
                       finished_at = CASE WHEN attempts >= max_attempts THEN now() END
                     WHERE status='LEASED' AND lease_expires_at < now()
                 RETURNING id, mission_id, type, status""").fetchall()
            for r in rows:
                emit(c, r["mission_id"], "TASK_FAILED",
                     {"task_id": r["id"], "type": r["type"], "error": "lease expired", "recovered_to": r["status"]})
            return len(rows)

    def cancel_mission(self, conn, mission_id: str) -> int:
        return conn.execute(
            "UPDATE tasks SET status='CANCELLED', finished_at=now(), lease_owner=NULL, lease_expires_at=NULL "
            "WHERE mission_id=%s AND status IN ('PENDING','LEASED')", (mission_id,)).rowcount

    # -- queries --------------------------------------------------------------
    @staticmethod
    def outstanding(conn, mission_id: str) -> int:
        return conn.execute(
            "SELECT count(*) AS n FROM tasks WHERE mission_id=%s AND status IN ('PENDING','LEASED')",
            (mission_id,)).fetchone()["n"]

    @staticmethod
    def counts(conn, mission_id: str) -> dict:
        rows = conn.execute("SELECT status, count(*) AS n FROM tasks WHERE mission_id=%s GROUP BY status",
                            (mission_id,)).fetchall()
        return {r["status"]: r["n"] for r in rows}


def is_terminal(status: str) -> bool:
    return status in {str(s) for s in TERMINAL_TASK}
