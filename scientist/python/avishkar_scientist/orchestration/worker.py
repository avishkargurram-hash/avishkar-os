"""Worker and supervisor loops (spec sections 4, 13, 50).

A worker leases one task at a time, dispatches it to `agents.handlers.HANDLERS`,
and reports success/failure back through the engine. The supervisor is a
separate, much simpler loop that only reclaims expired leases -- it owns no
business logic, so it can be a single process even with many workers.
"""

from __future__ import annotations

import logging
import time
from typing import Optional, Sequence

from ..domain import ALL_QUEUES
from ..tools.registry import ToolDenied, ToolError

log = logging.getLogger("scientist.worker")


def run_worker(ctx, name: str, queues: Sequence[str] = ALL_QUEUES, *, poll_s: float = 1.0,
               lease_s: Optional[int] = None, stop_after: Optional[int] = None,
               idle_limit: Optional[int] = None) -> int:
    """Processes tasks until `stop_after` tasks have been handled or
    `idle_limit` consecutive empty leases have elapsed (whichever first).
    With both None, runs forever (the production service entry point)."""
    from ..agents.handlers import HANDLERS
    lease_s = lease_s or ctx.settings.worker_lease_s
    processed = 0
    idle = 0
    while True:
        if stop_after is not None and processed >= stop_after:
            return processed
        tasks = ctx.engine.lease(name, queues, lease_s, limit=1)
        if not tasks:
            idle += 1
            if idle_limit is not None and idle >= idle_limit:
                return processed
            time.sleep(poll_s)
            continue
        idle = 0
        for t in tasks:
            handler = HANDLERS.get(t["type"])
            if handler is None:
                ctx.engine.fail(t["id"], name, f"no handler registered for task type {t['type']!r}",
                                retryable=False)
                processed += 1
                continue
            try:
                output, spawn = handler(ctx, t)
            except (ToolDenied, ToolError) as exc:
                log.warning("task %s (%s) tool error: %s", t["id"], t["type"], exc)
                ctx.engine.fail(t["id"], name, str(exc), retryable=True)
            except Exception as exc:  # noqa: BLE001 -- a handler bug must not crash the worker
                log.exception("task %s (%s) failed", t["id"], t["type"])
                ctx.engine.fail(t["id"], name, f"{type(exc).__name__}: {exc}", retryable=True)
            else:
                if not ctx.engine.complete(t["id"], name, output, spawn=spawn):
                    log.warning("task %s (%s) lease lost before completion", t["id"], t["type"])
            processed += 1
    return processed


def run_supervisor(ctx, *, interval_s: Optional[float] = None, stop_after_s: Optional[float] = None) -> None:
    """Periodically reclaims leases from crashed/stalled workers. Runs forever
    unless `stop_after_s` is given (used by tests)."""
    interval_s = interval_s or ctx.settings.supervisor_interval_s
    t0 = time.monotonic()
    while stop_after_s is None or time.monotonic() - t0 < stop_after_s:
        n = ctx.engine.recover_stale()
        if n:
            log.info("supervisor recovered %d stale lease(s)", n)
        time.sleep(interval_s)
