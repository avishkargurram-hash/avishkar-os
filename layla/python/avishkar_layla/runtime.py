"""ExecutiveRuntime -- composes every Layla component around the
explicit event-driven loop from Part IX:
IDLE -> EVENT -> INGEST -> UNDERSTAND -> DECIDE -> PLAN -> ACT/DELEGATE
-> VERIFY -> SLEEP/WAIT. See CONTRACT.md SS11.

handle_event() processes one event end to end, synchronously and
deterministically -- the unit this module's own tests exercise.
run_forever() is the actual "keep the lights on" entry point a real
deployment's process supervisor calls; see README.md Deployment for
why that loop itself is not exercised as a literal infinite loop in
tests (see README.md Testing Strategy for how the loop body is tested
instead -- run_forever(max_iterations=N) makes this a real, finite,
directly testable method rather than an untestable "trust me").
"""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping, Optional, Sequence, Tuple

from avishkar_agent import Orchestrator
from avishkar_core import get_logger
from avishkar_knowledge import KnowledgeBase

from .approval import ApprovalManager
from .audit import AuditLogger
from .auth import AuthorizationManager
from .capability_resolver import CapabilityResolver
from .context import ContextBuilder
from .delegation import DelegationEngine
from .errors import PermissionDeniedError, UnresolvedConflictError
from .execution import ExecutionTracker
from .identity import PERM_COMMAND, RISK_PERMISSION
from .intent import IntentInterpreter
from .memory_policy import LaylaMemoryPolicy
from .monitoring import HealthMonitor
from .notifications import NotificationManager
from .planning import Planner
from .risk import classify_risk
from .scheduler import Scheduler
from .session import SessionManager
from .state_machine import StateMachine
from .synthesis import ConflictResolver, ExecutiveSynthesizer, ResultValidator
from .types import (
    APPROVAL_PENDING,
    COMPLETED,
    CONTEXT_LOADING,
    DELEGATING,
    EXECUTING,
    PLANNING,
    REQUIRES_HUMAN,
    RISK_LOW,
    SYNTHESIZING,
    UNDERSTANDING,
    VERIFYING,
    WAITING,
    LaylaTask,
)


class ExecutiveRuntime:
    def __init__(
        self,
        *,
        orchestrator: Orchestrator,
        agent_domains: Mapping[str, str],
        memory: LaylaMemoryPolicy,
        approval_gate: Optional[Any] = None,
        authorization: Optional[AuthorizationManager] = None,
        execution_tracker: Optional[ExecutionTracker] = None,
        event_bus: Optional[Any] = None,
        knowledge_bases: Sequence[KnowledgeBase] = (),
        memory_lookups: Sequence[Tuple[str, str]] = (),
        scheduler: Optional[Scheduler] = None,
        clock: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
        logger: Optional[Any] = None,
    ) -> None:
        self._state_machine = StateMachine()
        self._intent = IntentInterpreter()
        self._context_builder = ContextBuilder()
        self._memory = memory
        self._memory_lookups = tuple(memory_lookups)
        self._knowledge_bases = tuple(knowledge_bases)

        self._capability_resolver = CapabilityResolver(agent_domains)
        self._planner = Planner(self._capability_resolver)

        self._authorization = authorization
        self._approval = ApprovalManager(approval_gate=approval_gate, authorization=authorization, clock=time.time)
        self._execution_tracker = execution_tracker
        self._delegation = DelegationEngine(
            orchestrator, approval_manager=self._approval, execution_tracker=execution_tracker,
            event_bus=event_bus, clock=clock, sleep_fn=sleep_fn,
        )
        self._validator = ResultValidator()
        self._conflicts = ConflictResolver()
        self._synthesizer = ExecutiveSynthesizer()

        self._session = SessionManager(memory)
        self._audit = AuditLogger(memory)
        self._notifications = NotificationManager()
        self._health = HealthMonitor(self._notifications)

        self._scheduler = scheduler
        self._sleep_fn = sleep_fn
        self._logger = logger or get_logger("layla.runtime")

    @property
    def notifications(self):
        return self._notifications

    @property
    def audit(self) -> AuditLogger:
        return self._audit

    @property
    def sessions(self) -> SessionManager:
        return self._session

    @property
    def executions(self) -> Optional[ExecutionTracker]:
        """The ExecutionTracker this runtime was constructed with, or
        None if idempotency tracking (Priority 17.2) wasn't wired in --
        callers use this to inspect/resolve_unknown() on an execution
        record after handle_event() returns, e.g. from a recovery script.
        """
        return self._execution_tracker

    def handle_event(self, input_text: str, *, session_id: Optional[str] = None) -> LaylaTask:
        """Processes one request end to end through the state machine.
        Deterministic and synchronous -- see module docstring.

        `session_id` (Priority 17.1, ADR-0021): when this runtime was
        constructed with an `authorization=`, a valid `session_id`
        holding PERM_COMMAND is required or this raises immediately,
        before a LaylaTask is even created -- an unauthenticated caller
        never gets as far as UNDERSTANDING. When no `authorization=`
        was supplied, `session_id` is accepted but ignored (Phase 16
        behavior, unchanged).
        """
        principal_id: Optional[str] = None
        if self._authorization is not None:
            session = self._authorization.require(session_id, PERM_COMMAND)
            principal_id = session.principal.id

        task = LaylaTask(input=input_text, principal_id=principal_id)
        self._audit.record("layla.task.received", {"input": input_text}, task_id=task.id, principal_id=principal_id)

        self._state_machine.transition(task, UNDERSTANDING)
        intent = self._intent.interpret(task.input)
        self._audit.record(
            "layla.intent.classified",
            {"category": intent.category, "urgency": intent.urgency, "requires_action": intent.requires_action},
            task_id=task.id, principal_id=principal_id,
        )

        self._state_machine.transition(task, CONTEXT_LOADING)
        task.context = self._context_builder.build(
            task, self._memory, memory_lookups=self._memory_lookups, knowledge_bases=self._knowledge_bases,
        )

        self._state_machine.transition(task, PLANNING)
        try:
            plan = self._planner.plan(task)
        except Exception as exc:  # noqa: BLE001 -- UnknownCapabilityError, normalized into REQUIRES_HUMAN
            task.blocked_reason = str(exc)
            self._state_machine.transition(task, REQUIRES_HUMAN)
            self._audit.record("layla.plan.failed", {"reason": str(exc)}, task_id=task.id, principal_id=principal_id)
            self._session.save(task)
            return task

        # Least-privilege capability enforcement (Priority 17.1 SS4): a
        # role may restrict which capabilities (agent names) a session
        # can invoke, independent of risk tier. Checked once, up front,
        # against every step -- a plan naming even one disallowed
        # capability is blocked in full rather than silently dropping
        # that step and proceeding partially.
        if self._authorization is not None:
            session = self._authorization.authenticate(session_id)
            for step in plan.steps:
                try:
                    self._authorization.authorize_capability(session, step.required_capability)
                except PermissionDeniedError as exc:
                    task.blocked_reason = str(exc)
                    self._state_machine.transition(task, REQUIRES_HUMAN)
                    self._audit.record(
                        "layla.plan.capability_denied", {"capability": step.required_capability},
                        task_id=task.id, principal_id=principal_id,
                    )
                    self._session.save(task)
                    return task

        task.plan_id = plan.id
        self._audit.record(
            "layla.plan.created", {"plan_id": plan.id, "step_count": len(plan.steps)},
            task_id=task.id, principal_id=principal_id,
        )

        overall_risk = classify_risk(task.input)
        if overall_risk != RISK_LOW:
            # Identity/risk integration point (Priority 17.1 SS3): a
            # session lacking the risk-appropriate permission is denied
            # outright -- Layla never even creates an ApprovalRequest
            # for an action this principal isn't allowed to ask for.
            if self._authorization is not None:
                session = self._authorization.authenticate(session_id)
                try:
                    self._authorization.authorize(session, RISK_PERMISSION[overall_risk])
                except PermissionDeniedError as exc:
                    task.blocked_reason = str(exc)
                    self._state_machine.transition(task, REQUIRES_HUMAN)
                    self._audit.record(
                        "layla.risk.permission_denied", {"risk_level": overall_risk},
                        task_id=task.id, principal_id=principal_id,
                    )
                    self._session.save(task)
                    return task

            self._state_machine.transition(task, APPROVAL_PENDING)
            approval = self._approval.request(
                task.id, f"execute plan {plan.id} for: {task.input}", overall_risk, requested_by=principal_id,
            )
            self._audit.record(
                "layla.approval.requested", {"approval_id": approval.id, "risk_level": overall_risk, "status": approval.status},
                task_id=task.id, principal_id=principal_id,
            )
            if approval.status != "granted":
                task.blocked_reason = f"approval {approval.id} status={approval.status}"
                self._state_machine.transition(task, REQUIRES_HUMAN)
                self._session.save(task)
                return task

        self._state_machine.transition(task, EXECUTING)
        self._session.save(task)

        self._state_machine.transition(task, DELEGATING)
        records = []
        for step in plan.steps:
            record = self._delegation.delegate(step, task_id=task.id, principal_id=principal_id)
            records.append(record)
            self._audit.record(
                f"layla.delegation.{record.status}",
                {"step_id": record.step_id, "agent_name": record.agent_name, "attempts": record.attempts},
                task_id=task.id, principal_id=principal_id,
            )
            self._health.observe_delegation(record)

        self._state_machine.transition(task, WAITING)
        self._state_machine.transition(task, VERIFYING)
        validation = self._validator.validate(records)
        self._audit.record(
            "layla.validation.completed", {"all_completed": validation.all_completed, "failing": list(validation.failing)},
            task_id=task.id, principal_id=principal_id,
        )

        self._state_machine.transition(task, SYNTHESIZING)
        conflicts = self._conflicts.detect(records)
        if conflicts:
            task.blocked_reason = f"{len(conflicts)} unresolved conflict(s) among delegated results"
            self._audit.record(
                "layla.conflict.detected", {"conflicts": [c.reason for c in conflicts]},
                task_id=task.id, principal_id=principal_id,
            )
            self._state_machine.transition(task, REQUIRES_HUMAN)
            self._session.save(task)
            return task

        try:
            summary = self._synthesizer.synthesize(records, conflicts)
        except UnresolvedConflictError as exc:  # pragma: no cover -- conflicts already handled above
            task.blocked_reason = str(exc)
            self._state_machine.transition(task, REQUIRES_HUMAN)
            self._session.save(task)
            return task

        task.result = summary
        self._state_machine.transition(task, COMPLETED)
        self._audit.record("layla.task.completed", {"result": summary}, task_id=task.id, principal_id=principal_id)
        self._session.save(task)
        return task

    def run_forever(self, *, max_iterations: Optional[int] = None, tick_interval_seconds: float = 1.0) -> int:
        """The real 24/7 entry point: repeatedly ticks the scheduler and
        sleeps. `max_iterations` makes this a real, finite, directly
        testable method rather than a literal infinite loop -- a
        deployment calls it with max_iterations=None (i.e. runs until
        the process is stopped by its supervisor). Returns the number
        of iterations actually run.
        """
        iterations = 0
        while max_iterations is None or iterations < max_iterations:
            if self._scheduler is not None:
                self._scheduler.tick()
            self._sleep_fn(tick_interval_seconds)
            iterations += 1
        return iterations
