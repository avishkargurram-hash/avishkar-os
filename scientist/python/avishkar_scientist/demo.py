"""Demo mode entry points (spec section 50).

The demo mission (`SCI-DEMO-001`) makes zero model and zero network calls --
every source, claim and experiment comes from `tools.mock`. It exists so the
whole pipeline (queues, evidence, contradictions, termination, verdict,
report) can be exercised and demonstrated with nothing configured.
"""

from __future__ import annotations

from . import mission as mission_mod
from .domain import ALL_QUEUES, TERMINAL_STATUSES
from .orchestration.worker import run_worker
from .tools.mock import DEMO_QUESTION


def run_demo(ctx) -> str:
    return mission_mod.create_mission(ctx.db, ctx.engine, DEMO_QUESTION, depth="STANDARD",
                                      demo=True, source="demo")


def run_demo_sync(ctx, *, max_tasks: int = 3000, poll_s: float = 0.02, idle_limit: int = 100) -> dict:
    """Runs the demo mission to completion in-process (one worker, no
    separate processes) and returns the final mission row. Used by the
    test-suite and by `cli.py demo`."""
    mid = run_demo(ctx)
    run_worker(ctx, "demo-worker", ALL_QUEUES, poll_s=poll_s, stop_after=max_tasks, idle_limit=idle_limit)
    return mission_mod.get_mission(ctx.db, mid)


def is_done(ctx, mid: str) -> bool:
    m = mission_mod.get_mission(ctx.db, mid)
    return bool(m) and m["status"] in TERMINAL_STATUSES
