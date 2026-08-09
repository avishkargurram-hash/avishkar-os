"""DelegationEngine -- wraps a real avishkar_agent.Orchestrator. See
CONTRACT.md SS5.

Every delegation is typed (PlanStep in, DelegationRecord out),
inspectable (record.status/.attempts/.started_at/.completed_at),
auditable (published via avishkar_core.EventBus when one is supplied),
permission-aware (checked against ApprovalManager first for MEDIUM/HIGH
risk steps), retryable (RetryPolicy reused from avishkar_integration --
the third framework to reuse it, after workflow-factory), and
timeout-aware (an elapsed-time check after the call returns -- see
CONTRACT.md SS5 and README.md Limitations for why this is a documented
non-preemptive boundary, not silently ignored).
"""

from __future__ import annotations

import dataclasses
import datetime
import time
from typing import Any, Callable, Optional

from avishkar_agent import NoMatchingAgentError, Orchestrator, Task
from avishkar_core import get_logger
from avishkar_integration import RetryPolicy

from .approval import ApprovalManager
from .types import RISK_LOW, DelegationRecord, PlanStep


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class DelegationEngine:
    def __init__(
        self,
        orchestrator: Orchestrator,
        *,
        approval_manager: Optional[ApprovalManager] = None,
        event_bus: Optional[Any] = None,
        clock: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
        logger: Optional[Any] = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._approval_manager = approval_manager
        self._event_bus = event_bus
        self._clock = clock
        self._sleep_fn = sleep_fn
        self._logger = logger or get_logger("layla.delegation")

    def delegate(self, plan_step: PlanStep, *, task_id: str) -> DelegationRecord:
        if self._approval_manager is not None and plan_step.risk_level != RISK_LOW:
            approval = self._approval_manager.request(
                task_id,
                f"delegate to capability '{plan_step.required_capability}': {plan_step.input}",
                plan_step.risk_level,
            )
            if approval.status != "granted":
                record = DelegationRecord(
                    step_id=plan_step.id, agent_name="", status="denied", started_at=_now(),
                )
                self._publish("layla.delegation.denied", record, task_id)
                return record

        retry_policy = RetryPolicy(max_attempts=max(1, plan_step.max_attempts))
        record = DelegationRecord(step_id=plan_step.id, agent_name="", status="pending", started_at=_now())

        for attempt in range(1, retry_policy.max_attempts + 1):
            record.attempts = attempt
            start = self._clock()
            try:
                result = self._orchestrator.route(
                    Task(input=plan_step.input, task_type=plan_step.required_capability)
                )
            except NoMatchingAgentError as exc:
                # No point retrying: the capability genuinely doesn't
                # resolve to any registered agent, regardless of attempt.
                record.status = "failed"
                record.error = str(exc)
                break
            except Exception as exc:  # noqa: BLE001 -- normalized into DelegationRecord, not swallowed
                record.error = str(exc)
                if attempt < retry_policy.max_attempts:
                    self._sleep_fn(retry_policy.backoff_seconds)
                    continue
                record.status = "failed"
                break

            elapsed = self._clock() - start
            if elapsed > plan_step.timeout_seconds:
                record.status = "timeout"
                record.error = f"call took {elapsed:.3f}s, exceeding timeout_seconds={plan_step.timeout_seconds}"
                break

            record.agent_name = result.agent_name
            record.output = result.output
            if result.status == "completed":
                record.status = "completed"
                record.completed_at = _now()
                break

            record.error = result.blocked_reason or f"agent status was {result.status!r}, not 'completed'"
            if attempt < retry_policy.max_attempts:
                self._sleep_fn(retry_policy.backoff_seconds)
                continue
            record.status = "failed"

        self._publish(
            f"layla.delegation.{record.status}", record, task_id,
        )
        return record

    def _publish(self, event_type: str, record: DelegationRecord, task_id: str) -> None:
        if self._event_bus is None:
            return
        payload = dataclasses.asdict(record)
        payload["task_id"] = task_id
        self._event_bus.publish(event_type, payload, source="layla.delegation")
