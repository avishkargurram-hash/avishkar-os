"""ExecutiveRuntime -- composes every Layla component around the
explicit event-driven loop from Part IX:
IDLE -> EVENT -> INGEST -> UNDERSTAND -> DECIDE -> PLAN -> ACT/DELEGATE
-> VERIFY -> SLEEP/WAIT. See CONTRACT.md SS11.

handle_event() processes one NEW request end to end, synchronously and
deterministically. resume() (Priority 17.3, ADR-0023) continues an
existing, persisted, non-terminal LaylaTask from exactly the state it
was last saved in -- both are thin entry points around the single
`_advance()` pipeline, which is itself resumable because every stage
is guarded by the task's CURRENT state rather than assumed to start
fresh; see CONTRACT.md SS17 for the checkpoint/resume contract this
implements. run_forever() is the actual "keep the lights on" entry
point a real deployment's process supervisor calls; see README.md
Deployment for why that loop itself is not exercised as a literal
infinite loop in tests (see README.md Testing Strategy for how the
loop body is tested instead -- run_forever(max_iterations=N) makes
this a real, finite, directly testable method rather than an
untestable "trust me").
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple

from avishkar_agent import Orchestrator
from avishkar_core import get_logger
from avishkar_knowledge import KnowledgeBase

from .approval import ApprovalManager
from .audit import AuditLogger
from .auth import AuthorizationManager
from .capability_resolver import CapabilityResolver
from .context import ContextBuilder
from .delegation import DelegationEngine
from .errors import PermissionDeniedError, SessionNotFoundError, UnresolvedConflictError
from .execution import ExecutionTracker
from .identity import PERM_COMMAND, RISK_PERMISSION
from .intent import IntentInterpreter
from .memory_policy import LaylaMemoryPolicy
from .monitoring import HealthMonitor
from .notifications import NotificationManager
from .personal_model import PersonalModel
from .planning import Planner
from .proactive import ProactiveEngine, ProactiveTrigger, TriggerEvaluator
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
    RECEIVED,
    REQUIRES_HUMAN,
    RISK_LOW,
    SYNTHESIZING,
    TERMINAL_STATES,
    UNDERSTANDING,
    VERIFYING,
    WAITING,
    LaylaTask,
    Plan,
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
        personal_model: Optional[PersonalModel] = None,
        enable_proactive: bool = False,
        proactive_evaluators: Sequence[TriggerEvaluator] = (),
        proactive_session_id: Optional[str] = None,
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
        # Mission Layla, Part 1 (ADR-0026): optional, additive -- omitted,
        # behavior is unchanged. Supplied, ContextBuilder folds a redacted
        # summary into every task's context (see context.py).
        self._personal_model = personal_model

        self._capability_resolver = CapabilityResolver(agent_domains)
        self._planner = Planner(self._capability_resolver)

        self._authorization = authorization
        # `memory=memory` (Priority 17.3, ADR-0023): ExecutiveRuntime
        # already requires a real `memory`, so ApprovalRequests are
        # durable by default -- a pending/decided approval survives a
        # restart, not just an in-process dict. See approval.py.
        self._approval = ApprovalManager(
            approval_gate=approval_gate, authorization=authorization, memory=memory, clock=time.time,
        )
        self._execution_tracker = execution_tracker
        # No `approval_manager=` here (Priority 17.3 fix, ADR-0023): the
        # task-level risk/approval decision in _advance() already fully
        # gates whether DELEGATING is ever reached at all -- every
        # PlanStep's risk_level is assigned from the same overall
        # classify_risk(task.input) call (see planning.py), so passing
        # the same ApprovalManager into DelegationEngine here would
        # create a SECOND, independent ApprovalRequest per step. That
        # was harmless as long as REQUIRES_HUMAN was a dead end (Phase
        # 16/17.1: an ungated pending task-level approval never reached
        # DELEGATING), but resume() (this priority) can now carry a
        # task-level-granted approval through to DELEGATING, where the
        # redundant per-step request -- never itself granted by anyone,
        # since its id was never surfaced -- would wrongly deny it. This
        # DelegationEngine still accepts `approval_manager=` for direct,
        # standalone use (see test_delegation.py); ExecutiveRuntime just
        # doesn't need or want a second gate on a decision it already
        # made.
        self._delegation = DelegationEngine(
            orchestrator, execution_tracker=execution_tracker, event_bus=event_bus, clock=clock, sleep_fn=sleep_fn,
        )
        self._validator = ResultValidator()
        self._conflicts = ConflictResolver()
        self._synthesizer = ExecutiveSynthesizer()

        self._session = SessionManager(memory)
        self._audit = AuditLogger(memory)
        self._notifications = NotificationManager()
        self._health = HealthMonitor(self._notifications)

        # Mission Layla, Part 2/11 (ADR-0026): optional, additive --
        # `enable_proactive=False` (default) means zero behavior change,
        # exactly like every other Phase 17/Mission Layla capability.
        # Constructed here, not accepted pre-built from the caller, so
        # its act_callback can bind straight to this runtime's own
        # handle_event() -- avoids a construction-order chicken-and-egg
        # problem (the engine needs a callback into the runtime; the
        # runtime is what's being constructed). See proactive.py and
        # _handle_proactive_act() below for why an ACT trigger always
        # goes through the full handle_event() pipeline, never a
        # shortcut.
        self._proactive_session_id = proactive_session_id
        self._proactive: Optional[ProactiveEngine] = None
        if enable_proactive:
            self._proactive = ProactiveEngine(
                self._session, self._audit, self._notifications,
                act_callback=self._handle_proactive_act, extra_evaluators=proactive_evaluators,
            )

        self._scheduler = scheduler
        self._sleep_fn = sleep_fn
        self._logger = logger or get_logger("layla.runtime")

        # Priority 17.4 (ADR-0024): one lock per task id, created
        # lazily and never removed (a bounded-lifetime deployment can
        # restart the process to reclaim it -- see README.md's
        # concurrency model for why per-task-id, not a single global
        # lock: two DIFFERENT tasks must be able to run _advance()
        # fully concurrently, e.g. "10 simultaneous tasks" or several
        # agents delegating in parallel; only two callers racing the
        # *same* task id (e.g. a duplicate event redelivery, or two
        # resume() calls after a flaky restart) need to be serialized.
        self._task_locks: Dict[str, threading.Lock] = {}
        self._task_locks_guard = threading.Lock()

    def _lock_for_task(self, task_id: str) -> threading.Lock:
        with self._task_locks_guard:
            lock = self._task_locks.get(task_id)
            if lock is None:
                lock = threading.Lock()
                self._task_locks[task_id] = lock
            return lock

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
    def proactive(self) -> Optional[ProactiveEngine]:
        """The ProactiveEngine this runtime constructed, or None if
        `enable_proactive=False` (the default) -- see Mission Layla
        Part 2/11. Exposed so a caller/test can invoke `.evaluate()`
        directly instead of only through `run_forever()`'s tick loop.
        """
        return self._proactive

    def _handle_proactive_act(self, trigger: ProactiveTrigger) -> None:
        """The one seam Layla's own proactive intelligence uses to turn
        a real trigger into a real action -- always the full
        handle_event() pipeline (UNDERSTANDING -> ... -> risk ->
        approval -> DELEGATING), never a bypass. If `authorization` is
        wired and no `proactive_session_id` was supplied at
        construction, this fails closed (UnauthenticatedError) rather
        than silently acting without a session -- Mission Layla Part 22
        ("fail closed, no silent bypass") applies to Layla's own
        self-triggered actions exactly as much as to a human's request.
        The failure is caught here (not left to crash run_forever()'s
        loop) and recorded via AuditLogger.
        """
        try:
            self.handle_event(trigger.description, session_id=self._proactive_session_id)
        except Exception as exc:  # noqa: BLE001 -- normalized into an audit record, not swallowed silently
            self._audit.record(
                "layla.proactive.act_failed",
                {"trigger_id": trigger.id, "description": trigger.description, "error": str(exc)},
                task_id=trigger.task_id,
            )

    @property
    def executions(self) -> Optional[ExecutionTracker]:
        """The ExecutionTracker this runtime was constructed with, or
        None if idempotency tracking (Priority 17.2) wasn't wired in --
        callers use this to inspect/resolve_unknown() on an execution
        record after handle_event()/resume() returns, e.g. from a
        recovery script.
        """
        return self._execution_tracker

    @property
    def personal_model(self) -> Optional[PersonalModel]:
        """The PersonalModel this runtime was constructed with, or None
        if not wired in (Mission Layla, Part 1) -- callers use this to
        read/write facts directly, e.g. from a settings UI or an
        onboarding flow.
        """
        return self._personal_model

    def handle_event(self, input_text: str, *, session_id: Optional[str] = None) -> LaylaTask:
        """Processes one NEW request end to end through the state
        machine. Deterministic and synchronous -- see module docstring.

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
        with self._lock_for_task(task.id):
            return self._advance(task, session_id=session_id)

    def resume(self, task_id: str, *, session_id: Optional[str] = None) -> LaylaTask:
        """Resume-in-place (Priority 17.3, ADR-0023): reloads a
        persisted LaylaTask by id and continues it from exactly the
        state it was last checkpointed in -- no re-planning (the Plan
        itself is persisted), no re-deciding an already-decided
        approval, and no duplicate delegation side effects when
        `execution_tracker` is wired (an already-COMPLETED step's
        ExecutionRecord makes DelegationEngine skip re-invoking the
        orchestrator for it -- see execution.py and CONTRACT.md SS15).
        Calling `resume()` is itself idempotent: a terminal or
        `REQUIRES_HUMAN` task is returned unchanged, never re-processed.

        Raises `SessionNotFoundError` if no task with this id was ever
        persisted. Raises `PermissionDeniedError` if `authorization` is
        wired and the resuming session belongs to a different principal
        than the one the task was originally created for.

        Concurrency (Priority 17.4, ADR-0024): the task is (re)loaded
        from durable storage *after* acquiring this task id's lock, not
        before -- two `resume()` calls racing the same task_id (a
        duplicate event redelivery, two recovery scripts started at
        once) would otherwise each load their own stale in-memory
        snapshot before either one's `_advance()` runs, and the second
        to actually execute would resume from an outdated state and
        redo work the first one already finished. Loading inside the
        lock means the second caller, once unblocked, re-reads
        whatever the first caller just persisted.
        """
        principal_id: Optional[str] = None
        if self._authorization is not None:
            session = self._authorization.require(session_id, PERM_COMMAND)
            principal_id = session.principal.id

        with self._lock_for_task(task_id):
            task = self._session.load(task_id)
            if task is None:
                raise SessionNotFoundError(f"no persisted task {task_id!r} to resume")

            if self._authorization is not None and task.principal_id is not None and task.principal_id != principal_id:
                raise PermissionDeniedError(
                    f"session principal {principal_id!r} may not resume task {task_id!r}, "
                    f"which was created for a different principal"
                )

            if task.state in TERMINAL_STATES or task.state == REQUIRES_HUMAN:
                # Nothing automatic to do: a terminal task is already
                # done; REQUIRES_HUMAN needs an explicit human decision
                # (fix the blocked_reason, grant/deny a stuck approval)
                # before any further automatic progress is safe to make.
                return task

            self._audit.record(
                "layla.task.resumed", {"from_state": task.state}, task_id=task.id, principal_id=task.principal_id,
            )
            return self._advance(task, session_id=session_id)

    def _advance(self, task: LaylaTask, *, session_id: Optional[str]) -> LaylaTask:
        """The single pipeline both handle_event() (task.state ==
        RECEIVED) and resume() (task.state == wherever it was last
        checkpointed) drive. Every stage is guarded by the task's
        CURRENT state -- transitioning it is what lets the *next*
        guard's condition become true, so a fresh task runs straight
        through exactly like Phase 16 did, while a resumed task skips
        directly to its first not-yet-done stage. See CONTRACT.md SS17.
        """
        principal_id = task.principal_id

        if task.state == RECEIVED:
            self._state_machine.transition(task, UNDERSTANDING)
            intent = self._intent.interpret(task.input)
            self._audit.record(
                "layla.intent.classified",
                {"category": intent.category, "urgency": intent.urgency, "requires_action": intent.requires_action},
                task_id=task.id, principal_id=principal_id,
            )

        if task.state == UNDERSTANDING:
            self._state_machine.transition(task, CONTEXT_LOADING)
            task.context = self._context_builder.build(
                task, self._memory, memory_lookups=self._memory_lookups, knowledge_bases=self._knowledge_bases,
                personal_model=self._personal_model,
            )

        if task.state == CONTEXT_LOADING:
            self._state_machine.transition(task, PLANNING)
            try:
                plan = self._planner.plan(task)
            except Exception as exc:  # noqa: BLE001 -- UnknownCapabilityError, normalized into REQUIRES_HUMAN
                task.blocked_reason = str(exc)
                self._state_machine.transition(task, REQUIRES_HUMAN)
                self._audit.record("layla.plan.failed", {"reason": str(exc)}, task_id=task.id, principal_id=principal_id)
                self._session.save(task)
                return task

            # Least-privilege capability enforcement (Priority 17.1 SS4):
            # a role may restrict which capabilities (agent names) a
            # session can invoke, independent of risk tier. Checked once,
            # up front, against every step -- a plan naming even one
            # disallowed capability is blocked in full rather than
            # silently dropping that step and proceeding partially.
            if self._authorization is not None:
                auth_session = self._authorization.authenticate(session_id)
                for step in plan.steps:
                    try:
                        self._authorization.authorize_capability(auth_session, step.required_capability)
                    except PermissionDeniedError as exc:
                        task.blocked_reason = str(exc)
                        self._state_machine.transition(task, REQUIRES_HUMAN)
                        self._audit.record(
                            "layla.plan.capability_denied", {"capability": step.required_capability},
                            task_id=task.id, principal_id=principal_id,
                        )
                        self._session.save(task)
                        return task

            task.plan = plan
            task.plan_id = plan.id
            self._audit.record(
                "layla.plan.created", {"plan_id": plan.id, "step_count": len(plan.steps)},
                task_id=task.id, principal_id=principal_id,
            )
            # Durable checkpoint (Priority 17.3): the plan itself is now
            # safe to resume from -- a crash from here on never needs to
            # re-plan, only to continue with the same steps.
            self._session.save(task)

        plan: Optional[Plan] = task.plan  # populated just above, or (on resume) by an earlier save

        if task.state == PLANNING:
            overall_risk = classify_risk(task.input)
            if overall_risk == RISK_LOW:
                self._state_machine.transition(task, EXECUTING)
            else:
                # Identity/risk integration point (Priority 17.1 SS3): a
                # session lacking the risk-appropriate permission is
                # denied outright -- Layla never even creates an
                # ApprovalRequest for an action this principal isn't
                # allowed to ask for.
                if self._authorization is not None:
                    auth_session = self._authorization.authenticate(session_id)
                    try:
                        self._authorization.authorize(auth_session, RISK_PERMISSION[overall_risk])
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
                task.pending_approval_id = approval.id
                self._audit.record(
                    "layla.approval.requested",
                    {"approval_id": approval.id, "risk_level": overall_risk, "status": approval.status},
                    task_id=task.id, principal_id=principal_id,
                )
                # Durable checkpoint (Priority 17.3): a real, persisted
                # APPROVAL_PENDING state -- resume() re-checks the same
                # approval id rather than silently re-requesting a new
                # one or giving up. See CONTRACT.md SS17 "interrupted
                # approval."
                self._session.save(task)

        if task.state == APPROVAL_PENDING:
            status = self._approval.check(task.pending_approval_id)
            if status == "granted":
                self._state_machine.transition(task, EXECUTING)
            elif status == "pending":
                # Still waiting on a human/gate decision -- not a
                # failure, just not ready yet. Caller (or a scheduled
                # retry) calls resume() again later.
                return task
            else:  # "denied" or "expired"
                task.blocked_reason = f"approval {task.pending_approval_id} status={status}"
                self._state_machine.transition(task, REQUIRES_HUMAN)
                self._session.save(task)
                return task

        if task.state == EXECUTING:
            # Durable checkpoint (Priority 17.3): everything before this
            # point is pure, cheap, and side-effect-free to redo; from
            # here on, delegation can have real external effects, so the
            # task is saved *before* the first delegate() call, not
            # after.
            self._session.save(task)

            self._state_machine.transition(task, DELEGATING)
            records = []
            for step in plan.steps:
                # Idempotency (Priority 17.2): if execution_tracker is
                # wired, a step already COMPLETED from a prior attempt
                # (e.g. a crash after step 17 of 50, resumed here) is
                # returned from cache without invoking the orchestrator
                # again -- see execution.py and CONTRACT.md SS15. Without
                # it, a resumed DELEGATING phase re-runs every step, the
                # same as any other optional-capability-omitted default.
                record = self._delegation.delegate(step, task_id=task.id, principal_id=principal_id)
                records.append(record)
                self._audit.record(
                    f"layla.delegation.{record.status}",
                    {"step_id": record.step_id, "agent_name": record.agent_name, "attempts": record.attempts,
                     "cost_usd": record.cost_usd},
                    task_id=task.id, principal_id=principal_id,
                )
                self._health.observe_delegation(record)

            self._state_machine.transition(task, WAITING)
            self._state_machine.transition(task, VERIFYING)
            validation = self._validator.validate(records)
            self._audit.record(
                "layla.validation.completed",
                {"all_completed": validation.all_completed, "failing": list(validation.failing)},
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
        """The real 24/7 entry point: repeatedly ticks the scheduler,
        evaluates proactive intelligence (if enabled), and sleeps.
        `max_iterations` makes this a real, finite, directly testable
        method rather than a literal infinite loop -- a deployment
        calls it with max_iterations=None (i.e. runs until the process
        is stopped by its supervisor). Returns the number of iterations
        actually run.

        This is the concrete SLEEP -> EVENT -> WAKE -> ... -> SLEEP
        cycle from Mission Layla Part 11: `_proactive.evaluate()` is
        cheap Python over already-recorded state (SessionManager/
        AuditLogger), never an LLM call by itself -- only an ACT-level
        trigger causes `_handle_proactive_act()` to call the real
        `handle_event()` pipeline. A slow ACT-triggered call delays the
        next scheduler tick until it returns -- this runtime has no
        async/background-task model (Phase 17.4's concurrency guarantees
        are thread-based, not async-based), a known, documented
        limitation, not an oversight.
        """
        iterations = 0
        while max_iterations is None or iterations < max_iterations:
            if self._scheduler is not None:
                self._scheduler.tick()
            if self._proactive is not None:
                self._proactive.evaluate()
            self._sleep_fn(tick_interval_seconds)
            iterations += 1
        return iterations
