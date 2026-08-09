"""Scheduler -- a real, in-process, min-heap-backed scheduler. See
CONTRACT.md SS7.

Does not run a background thread/process itself -- see
ExecutiveRuntime.run_forever() for the actual "keep calling tick()"
loop, and README.md Deployment for what real 24/7 operation requires.
Injectable clock -- the same DI seam security-factory's rate limiter
and mcp-factory's retry backoff already use -- so scheduling logic is
deterministically testable without real wall-clock waits.
"""

from __future__ import annotations

import heapq
import time
from typing import Callable, Dict, List, Optional, Tuple

from .types import ScheduledJob, new_id


class Scheduler:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._heap: List[Tuple[float, str]] = []
        self._jobs: Dict[str, ScheduledJob] = {}
        self._callbacks: Dict[str, Callable[[], None]] = {}

    def schedule_once(self, at: float, callback: Callable[[], None]) -> str:
        job_id = new_id("job")
        self._jobs[job_id] = ScheduledJob(id=job_id, run_at=at, interval_seconds=None)
        self._callbacks[job_id] = callback
        heapq.heappush(self._heap, (at, job_id))
        return job_id

    def schedule_recurring(
        self, interval_seconds: float, callback: Callable[[], None], *, start_at: Optional[float] = None
    ) -> str:
        job_id = new_id("job")
        at = start_at if start_at is not None else self._clock() + interval_seconds
        self._jobs[job_id] = ScheduledJob(id=job_id, run_at=at, interval_seconds=interval_seconds)
        self._callbacks[job_id] = callback
        heapq.heappush(self._heap, (at, job_id))
        return job_id

    def cancel(self, job_id: str) -> bool:
        """Lazy deletion: removes the job's bookkeeping now; the stale
        heap entry (if any) is silently skipped by tick() when its turn
        comes, rather than requiring an O(n) heap search here.
        """
        if job_id in self._jobs:
            del self._jobs[job_id]
            del self._callbacks[job_id]
            return True
        return False

    def pending_job_ids(self) -> Tuple[str, ...]:
        return tuple(self._jobs.keys())

    def tick(self, now: Optional[float] = None) -> Tuple[str, ...]:
        """Runs every job whose run_at <= now, rescheduling recurring
        jobs for their next interval. Returns the ids that fired.
        """
        now = now if now is not None else self._clock()
        fired = []
        while self._heap and self._heap[0][0] <= now:
            run_at, job_id = heapq.heappop(self._heap)
            job = self._jobs.get(job_id)
            if job is None:
                continue  # cancelled since being scheduled
            self._callbacks[job_id]()
            fired.append(job_id)
            if job.interval_seconds is not None:
                next_at = run_at + job.interval_seconds
                self._jobs[job_id] = ScheduledJob(id=job_id, run_at=next_at, interval_seconds=job.interval_seconds)
                heapq.heappush(self._heap, (next_at, job_id))
            else:
                del self._jobs[job_id]
                del self._callbacks[job_id]
        return tuple(fired)
