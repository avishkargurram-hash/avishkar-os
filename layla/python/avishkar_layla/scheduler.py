"""Scheduler -- a real, in-process, min-heap-backed scheduler. See
CONTRACT.md SS7.

Does not run a background thread/process itself -- see
ExecutiveRuntime.run_forever() for the actual "keep calling tick()"
loop, and README.md Deployment for what real 24/7 operation requires.
Injectable clock -- the same DI seam security-factory's rate limiter
and mcp-factory's retry backoff already use -- so scheduling logic is
deterministically testable without real wall-clock waits.

Concurrency (Priority 17.4, ADR-0024): `_heap`/`_jobs`/`_callbacks` are
guarded by a single lock. `tick()` running on one thread while another
schedules/cancels a job is a real race otherwise -- `heapq` itself
isn't documented as thread-safe for concurrent push/pop, and even
where the GIL happens to prevent a crash, `cancel()` racing `tick()`
could let an already-cancelled job's callback fire anyway, or a
`schedule_once()` call's bookkeeping could interleave with `tick()`'s
cleanup of a *different* job and corrupt `_jobs`/`_callbacks`. A job's
own `callback()` is invoked *outside* the lock -- holding it during an
arbitrary callback would block every other scheduler operation for as
long as that callback runs, and a callback that itself calls back into
the scheduler (e.g. rescheduling itself) would deadlock on a
non-reentrant lock.
"""

from __future__ import annotations

import heapq
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

from .types import ScheduledJob, new_id


class Scheduler:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._heap: List[Tuple[float, str]] = []
        self._jobs: Dict[str, ScheduledJob] = {}
        self._callbacks: Dict[str, Callable[[], None]] = {}
        self._lock = threading.Lock()

    def schedule_once(self, at: float, callback: Callable[[], None]) -> str:
        job_id = new_id("job")
        with self._lock:
            self._jobs[job_id] = ScheduledJob(id=job_id, run_at=at, interval_seconds=None)
            self._callbacks[job_id] = callback
            heapq.heappush(self._heap, (at, job_id))
        return job_id

    def schedule_recurring(
        self, interval_seconds: float, callback: Callable[[], None], *, start_at: Optional[float] = None
    ) -> str:
        job_id = new_id("job")
        at = start_at if start_at is not None else self._clock() + interval_seconds
        with self._lock:
            self._jobs[job_id] = ScheduledJob(id=job_id, run_at=at, interval_seconds=interval_seconds)
            self._callbacks[job_id] = callback
            heapq.heappush(self._heap, (at, job_id))
        return job_id

    def cancel(self, job_id: str) -> bool:
        """Lazy deletion: removes the job's bookkeeping now; the stale
        heap entry (if any) is silently skipped by tick() when its turn
        comes, rather than requiring an O(n) heap search here.
        """
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                del self._callbacks[job_id]
                return True
            return False

    def pending_job_ids(self) -> Tuple[str, ...]:
        with self._lock:
            return tuple(self._jobs.keys())

    def tick(self, now: Optional[float] = None) -> Tuple[str, ...]:
        """Runs every job whose run_at <= now, rescheduling recurring
        jobs for their next interval. Returns the ids that fired.

        Duplicate-execution safety: a job popped off the heap is looked
        up in `_jobs` *while holding the lock*, and a cancelled job (not
        in `_jobs`) is skipped -- a `cancel()` racing this exact instant
        from another thread sees a consistent, not a half-updated,
        `_jobs` (both use the same lock). Each individual job's due-check
        + pop + callback-lookup + reschedule/cleanup is atomic; the
        callback itself runs unlocked (see module docstring).
        """
        now = now if now is not None else self._clock()
        fired = []
        while True:
            with self._lock:
                if not self._heap or self._heap[0][0] > now:
                    break
                run_at, job_id = heapq.heappop(self._heap)
                job = self._jobs.get(job_id)
                if job is None:
                    continue  # cancelled since being scheduled
                callback = self._callbacks[job_id]
                if job.interval_seconds is not None:
                    next_at = run_at + job.interval_seconds
                    self._jobs[job_id] = ScheduledJob(id=job_id, run_at=next_at, interval_seconds=job.interval_seconds)
                    heapq.heappush(self._heap, (next_at, job_id))
                else:
                    del self._jobs[job_id]
                    del self._callbacks[job_id]

            callback()  # deliberately outside the lock -- see module docstring
            fired.append(job_id)
        return tuple(fired)
