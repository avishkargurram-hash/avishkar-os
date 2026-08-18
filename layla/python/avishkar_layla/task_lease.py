"""TaskLeaseManager -- Mission Layla Directive D, Part XII (Durable
Execution: task ownership, stale-task recovery). See CONTRACT.md SS50.

Most of "durable execution" is already real, existing functionality,
not rebuilt here: durable task state and checkpoints (`SessionManager`/
`LaylaTask.plan`, Priority 17.3, ADR-0023), idempotency keys and
exactly-once-or-safe-at-least-once semantics (`ExecutionTracker`,
Priority 17.2, ADR-0022), retry policies (`DelegationEngine`), an
execution journal (`AuditLogger`). This module's real, new
contribution is the two items Directive D Part XII names that nothing
existing covers: task OWNERSHIP and STALE-TASK recovery -- "A machine
restart must NOT destroy an important Layla task," and, this module's
specific addition, a restarting process should be able to tell WHICH
incomplete tasks were actively being worked on when the previous
process died (a stale lease) versus simply queued and never started.

STATUS: REAL, with an explicitly documented scope limit. `TaskLeaseManager`
is thread-safe within one process (a `threading.Lock` guards the
check-then-write, the same pattern `Scheduler`/`AuditLogger` already
use) and durable across a restart (leases are persisted via the real
`LaylaMemoryPolicy`, so a new process can see what the old one had
claimed). It is NOT a distributed lock service: true atomicity across
*multiple concurrent OS processes* racing to acquire the same lease
depends on the underlying `LaylaMemoryPolicy` backend's own guarantees,
which this layer does not itself provide (`remember()` is an
unconditional write, not a compare-and-swap). This is the honest,
correctly-scoped answer for the realistic deployment model Directive D
Part XI/XII actually describes -- one active Layla process, restarted
by a supervisor after a crash -- not a claim of solving general
distributed mutual exclusion.
"""

from __future__ import annotations

import dataclasses
import datetime
import threading
import time
from typing import Callable, Optional, Sequence, Tuple

from .memory_policy import LaylaMemoryPolicy

_KIND = "episodic"


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _key(task_id: str) -> str:
    return f"lease:{task_id}"


@dataclasses.dataclass(frozen=True)
class TaskLease:
    task_id: str
    worker_id: str
    acquired_at: str
    expires_at: float  # a real value from the manager's own clock() -- comparable only against that same clock


class TaskLeaseManager:
    def __init__(self, memory: LaylaMemoryPolicy, *, clock: Callable[[], float] = time.time) -> None:
        self._memory = memory
        self._clock = clock
        self._lock = threading.Lock()

    def acquire(self, task_id: str, worker_id: str, *, lease_seconds: float = 300.0) -> bool:
        """Real claim: succeeds if no lease exists, the existing lease
        is already held by this same `worker_id` (idempotent
        re-acquire/renew), or the existing lease has expired (real
        stale-lease takeover). Fails only against a real,
        currently-unexpired lease held by a genuinely different
        worker.
        """
        with self._lock:
            now = self._clock()
            existing = self._memory.recall(_KIND, _key(task_id))
            if existing is not None:
                value = existing.value
                if value["worker_id"] != worker_id and value["expires_at"] > now:
                    return False
            self._memory.remember(
                _KIND, _key(task_id),
                {"task_id": task_id, "worker_id": worker_id, "acquired_at": _now_iso(), "expires_at": now + lease_seconds},
                provenance="task-lease-manager",
            )
            return True

    def renew(self, task_id: str, worker_id: str, *, lease_seconds: float = 300.0) -> bool:
        """Extends a lease this `worker_id` currently holds. Refuses
        (returns False, never raises) for a lease held by someone
        else or a task with no lease at all -- a worker cannot renew
        what it never legitimately acquired.
        """
        with self._lock:
            existing = self._memory.recall(_KIND, _key(task_id))
            if existing is None or existing.value["worker_id"] != worker_id:
                return False
            now = self._clock()
            self._memory.remember(
                _KIND, _key(task_id),
                {
                    "task_id": task_id, "worker_id": worker_id, "acquired_at": existing.value["acquired_at"],
                    "expires_at": now + lease_seconds,
                },
                provenance="task-lease-manager",
            )
            return True

    def release(self, task_id: str, worker_id: str) -> bool:
        """Real, explicit release -- a worker that finished (or is
        gracefully giving up on) a task calls this so a *different*
        worker doesn't have to wait out the full lease duration before
        recognizing the task is free again.
        """
        with self._lock:
            existing = self._memory.recall(_KIND, _key(task_id))
            if existing is None or existing.value["worker_id"] != worker_id:
                return False
            self._memory.forget(_KIND, _key(task_id))
            return True

    def get_lease(self, task_id: str) -> Optional[TaskLease]:
        record = self._memory.recall(_KIND, _key(task_id))
        if record is None:
            return None
        value = record.value
        return TaskLease(
            task_id=value["task_id"], worker_id=value["worker_id"], acquired_at=value["acquired_at"],
            expires_at=value["expires_at"],
        )

    def is_stale(self, task_id: str, *, now: Optional[float] = None) -> bool:
        """A task with NO lease at all is not "stale" -- it was simply
        never claimed (or was cleanly released). Only a real, expired,
        still-recorded lease counts as stale -- the "a worker claimed
        this and then died without releasing it" signal.
        """
        lease = self.get_lease(task_id)
        if lease is None:
            return False
        now = now if now is not None else self._clock()
        return lease.expires_at <= now

    def find_stale_leases(self, task_ids: Sequence[str], *, now: Optional[float] = None) -> Tuple[str, ...]:
        """Real convenience over `is_stale()` for a batch of candidate
        task ids -- the intended real usage is
        `find_stale_leases(t.id for t in session_manager.list_incomplete())`
        on process startup, to distinguish "genuinely stuck, safe to
        resume" incomplete tasks from ones another still-live worker
        may legitimately be mid-processing right now.
        """
        now = now if now is not None else self._clock()
        return tuple(task_id for task_id in task_ids if self.is_stale(task_id, now=now))
