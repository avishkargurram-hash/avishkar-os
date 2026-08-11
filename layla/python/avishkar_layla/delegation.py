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

Idempotency (Priority 17.2, ADR-0022): `execution_tracker` is an
*optional* constructor argument, the same additive pattern
`approval_manager=`/`authorization=` already established. Omitted:
behavior is unchanged from Phase 16/17.1. Supplied: every delegation is
tracked under a real `ExecutionRecord` keyed `{task_id}:{step.id}` --
a completed delegation short-circuits (the orchestrator is never
called again for the same key); a delegation any other in-flight
attempt already claimed (AUTHORIZED/APPROVED/EXECUTING/UNKNOWN) refuses
to proceed for a non-READ operation rather than risk a duplicate side
effect; a timeout on a non-READ operation is recorded UNKNOWN, not
FAILED, because FAILED would imply "safe to retry" and a timeout does
not guarantee that.
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
from .execution import (
    EXEC_APPROVED,
    EXEC_AUTHORIZED,
    EXEC_COMPLETED,
    EXEC_EXECUTING,
    EXEC_FAILED,
    EXEC_REJECTED,
    EXEC_REQUESTED,
    EXEC_UNKNOWN,
    OP_READ,
    ExecutionTracker,
    classify_operation,
)
from .types import RISK_LOW, DelegationRecord, PlanStep

# Priority 17.4 (ADR-0024): EXEC_REQUESTED is included here, not just
# AUTHORIZED/APPROVED/EXECUTING/UNKNOWN. begin() (execution.py) is now
# atomic w.r.t. other begin() calls on the same key -- only the FIRST
# concurrent caller for a brand-new key ever observes "no existing
# record" and creates one. A second, truly concurrent caller for the
# same key observes that just-created REQUESTED record and must be
# refused here exactly like AUTHORIZED/EXECUTING/UNKNOWN -- otherwise
# two threads racing delegate() for the same key would both proceed to
# invoke the orchestrator, which is precisely the duplicate-side-effect
# idempotency exists to prevent.
_CLAIMED_NON_TERMINAL_STATES = frozenset(
    {EXEC_REQUESTED, EXEC_AUTHORIZED, EXEC_APPROVED, EXEC_EXECUTING, EXEC_UNKNOWN}
)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class DelegationEngine:
    def __init__(
        self,
        orchestrator: Orchestrator,
        *,
        approval_manager: Optional[ApprovalManager] = None,
        execution_tracker: Optional[ExecutionTracker] = None,
        event_bus: Optional[Any] = None,
        clock: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
        logger: Optional[Any] = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._approval_manager = approval_manager
        self._execution_tracker = execution_tracker
        self._event_bus = event_bus
        self._clock = clock
        self._sleep_fn = sleep_fn
        self._logger = logger or get_logger("layla.delegation")

    def delegate(self, plan_step: PlanStep, *, task_id: str, principal_id: Optional[str] = None) -> DelegationRecord:
        idempotency_key = f"{task_id}:{plan_step.id}"
        operation_kind = classify_operation(plan_step.input)

        if self._execution_tracker is not None:
            existing = self._execution_tracker.begin(idempotency_key, operation_kind, plan_step.input)
            if existing.status == EXEC_COMPLETED:
                cached = existing.result or {}
                return DelegationRecord(
                    step_id=plan_step.id, agent_name=cached.get("agent_name", ""), status="completed",
                    output=cached.get("output"), attempts=existing.attempts, completed_at=existing.updated_at,
                )
            # `claimed_this_call` (Priority 17.4) distinguishes "my own
            # begin() call just created this REQUESTED record, proceed"
            # from "someone else already claimed this key" -- both look
            # identical by .status alone (EXEC_REQUESTED either way).
            just_claimed = getattr(existing, "claimed_this_call", False)
            if not just_claimed and existing.status in _CLAIMED_NON_TERMINAL_STATES and operation_kind != OP_READ:
                return DelegationRecord(
                    step_id=plan_step.id, agent_name="", status="failed",
                    error=(
                        f"idempotency key {idempotency_key!r} is already {existing.status} from a prior "
                        f"attempt that never reached a terminal state -- refusing to risk a duplicate "
                        f"{operation_kind} side effect; resolve it explicitly first "
                        f"(ExecutionTracker.resolve_unknown() if UNKNOWN)"
                    ),
                )

        if self._approval_manager is not None and plan_step.risk_level != RISK_LOW:
            approval = self._approval_manager.request(
                task_id,
                f"delegate to capability '{plan_step.required_capability}': {plan_step.input}",
                plan_step.risk_level,
                requested_by=principal_id,
            )
            if approval.status != "granted":
                record = DelegationRecord(
                    step_id=plan_step.id, agent_name="", status="denied", started_at=_now(),
                )
                if self._execution_tracker is not None:
                    self._execution_tracker.transition(idempotency_key, EXEC_REJECTED, error="approval not granted")
                self._publish("layla.delegation.denied", record, task_id, principal_id)
                return record

        if self._execution_tracker is not None:
            # Two real, recorded transitions -- matching Priority 17.2's
            # explicit REQUESTED -> AUTHORIZED -> APPROVED lifecycle,
            # even though this DelegationEngine's own approval check is
            # the single decision point both map to.
            self._execution_tracker.transition(idempotency_key, EXEC_AUTHORIZED)
            self._execution_tracker.transition(idempotency_key, EXEC_APPROVED)
            self._execution_tracker.transition(idempotency_key, EXEC_EXECUTING)

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

        if self._execution_tracker is not None:
            if record.status == "completed":
                self._execution_tracker.transition(
                    idempotency_key, EXEC_COMPLETED,
                    result={"agent_name": record.agent_name, "output": record.output},
                    increment_attempts=True,
                )
            elif record.status == "timeout" and operation_kind != OP_READ:
                # Genuinely uncertain -- the delegated agent/tool call
                # may have partially executed. UNKNOWN, not FAILED:
                # FAILED would imply "safe to retry," which a timeout on
                # a WRITE/HIGH_RISK operation does not guarantee.
                self._execution_tracker.transition(idempotency_key, EXEC_UNKNOWN, error=record.error, increment_attempts=True)
            else:
                self._execution_tracker.transition(idempotency_key, EXEC_FAILED, error=record.error, increment_attempts=True)

        self._publish(
            f"layla.delegation.{record.status}", record, task_id, principal_id,
        )
        return record

    def _publish(self, event_type: str, record: DelegationRecord, task_id: str, principal_id: Optional[str] = None) -> None:
        if self._event_bus is None:
            return
        payload = dataclasses.asdict(record)
        payload["task_id"] = task_id
        payload["principal_id"] = principal_id
        self._event_bus.publish(event_type, payload, source="layla.delegation")
