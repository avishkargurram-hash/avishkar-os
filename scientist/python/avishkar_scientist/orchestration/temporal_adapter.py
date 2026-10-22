"""TemporalAdapter -- the documented migration path (ADR-0046 decision 1).

Scientist OS runs on PgWorkflowEngine today: one small VPS, no extra
daemons, the same Postgres that already holds the evidence graph. If load
outgrows it (many concurrent EXTREME missions, multi-host workers), the
`WorkflowEngine` contract maps onto Temporal 1:1:

    enqueue        -> workflow.execute_activity / start child workflow
    lease          -> Temporal task-queue poll (worker.run)
    heartbeat      -> activity.heartbeat(details)          (checkpoint = details)
    complete/fail  -> activity return / raise ApplicationError(non_retryable=...)
    recover_stale  -> built in (heartbeat_timeout + retry policy)
    cancel_mission -> workflow handle .cancel()

Handlers (agents/handlers.py) are plain functions of (ctx, input) -> output
and never touch the engine directly, so they move unchanged. This class
exists so the swap is a constructor change, and fails loudly if selected
without temporalio installed instead of silently degrading.
"""

from __future__ import annotations

from .engine import WorkflowEngine


class TemporalAdapter(WorkflowEngine):  # pragma: no cover -- not deployed
    def __init__(self, *_, **__):
        try:
            import temporalio  # noqa: F401
        except Exception as exc:
            raise RuntimeError(
                "TemporalAdapter selected but temporalio is not installed; "
                "Scientist OS runs on PgWorkflowEngine (see ADR-0046)") from exc
        raise NotImplementedError("Temporal backend is a documented migration path, not deployed")

    def enqueue(self, conn, mission_id, spec): raise NotImplementedError
    def lease(self, worker, queues, lease_s, limit=1): raise NotImplementedError
    def heartbeat(self, task_id, worker, lease_s): raise NotImplementedError
    def complete(self, task_id, worker, output, spawn=()): raise NotImplementedError
    def fail(self, task_id, worker, error, retryable=True): raise NotImplementedError
    def recover_stale(self): raise NotImplementedError
    def cancel_mission(self, conn, mission_id): raise NotImplementedError
