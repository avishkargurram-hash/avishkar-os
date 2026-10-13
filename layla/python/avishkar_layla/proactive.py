"""ProactiveEngine -- Layla's proactive intelligence and persistent-
runtime orchestration layer. See CONTRACT.md SS21, ADR-0026, Mission
Layla directive Parts 2 and 11.

Combines two roles the directive treats separately but which are, in
this architecture, the same mechanism: "should Layla act right now
without being asked" (Part 2, Proactive Intelligence) IS the decision
that drives Layla's SLEEP -> EVENT -> WAKE -> ... -> SLEEP persistent-
runtime cycle (Part 11) -- a `Scheduler` tick is the EVENT; `evaluate()`
is WAKE+CONTEXT+DECIDE; the emitted `ProactiveAction`s are ACT (or a
deliberate non-act). No LLM is called merely to check "did anything
change" -- every trigger evaluator here inspects real, already-recorded
system state (SessionManager/AuditLogger) via cheap Python, and only an
`ACT`-level trigger ever causes `ExecutiveRuntime.handle_event()` (and
therefore a real LLM/agent call) to run. This is the concrete answer to
Part 20/21's "wake an LLM only when cognition is required."

Every trigger emitted here carries real evidence (the actual audit
records or task ids it was computed from) -- never a fabricated
prediction. Compare GENESIS's `core/prediction/*.py`, confirmed by this
mission's own forensic audit to return hardcoded literal dicts
regardless of input; this module is a deliberate, from-scratch,
evidence-only reimplementation of the *pattern* GENESIS's
`proactive_engine.py` and `environment_prediction/` got right (real
trigger conditions, real computed data) without reusing any GENESIS
code, data, or fake-confidence conventions.

Action levels (Mission Layla directive Part 2): IGNORE (no trigger --
evaluate() simply returns nothing), OBSERVE (recorded via AuditLogger,
never surfaced to the user), SUGGEST/ASK (a Notification, never an
autonomous side effect), ACT (drives a real, fully risk/approval-gated
`handle_event()` call -- never a shortcut around Layla's existing
pipeline), URGENTLY_ALERT (a CRITICAL Notification). There is no
"silently act without going through handle_event()" path -- an ACT
trigger still passes through UNDERSTANDING/PLANNING/risk/approval/
DELEGATING exactly like a user-issued request would.
"""

from __future__ import annotations

import dataclasses
import datetime
import time
from typing import Any, Callable, List, Optional, Sequence, Tuple

from .audit import AuditLogger
from .notifications import NotificationManager
from .session import SessionManager
from .types import (
    REQUIRES_HUMAN,
    SEVERITY_ACTION_REQUIRED,
    SEVERITY_CRITICAL,
)

ACTION_IGNORE = "IGNORE"
ACTION_OBSERVE = "OBSERVE"
ACTION_SUGGEST = "SUGGEST"
ACTION_ASK = "ASK"
ACTION_ACT = "ACT"
ACTION_URGENTLY_ALERT = "URGENTLY_ALERT"

_ACTION_LEVELS = (ACTION_IGNORE, ACTION_OBSERVE, ACTION_SUGGEST, ACTION_ASK, ACTION_ACT, ACTION_URGENTLY_ALERT)

# How long a REQUIRES_HUMAN task can sit unresolved before each action
# level fires -- SUGGEST first, escalating to URGENTLY_ALERT. Injectable
# via ProactiveEngine's constructor, these are not hidden magic numbers.
_DEFAULT_STUCK_SUGGEST_SECONDS = 3600.0
_DEFAULT_STUCK_ALERT_SECONDS = 86400.0
# How many delegation failures for the same task, within its own audit
# history, before the pattern is worth surfacing at all (OBSERVE) versus
# escalating to a human-visible SUGGEST.
_DEFAULT_FAILURE_OBSERVE_THRESHOLD = 2
_DEFAULT_FAILURE_SUGGEST_THRESHOLD = 3


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@dataclasses.dataclass(frozen=True)
class ProactiveTrigger:
    """One real, evidence-backed reason Layla might act. `evidence` is
    always the actual data the trigger was computed from (task ids,
    audit event counts, timestamps) -- never a free-text guess.
    """

    id: str
    action_level: str
    description: str
    evidence: Any
    source: str  # which evaluator produced this trigger
    task_id: Optional[str] = None


TriggerEvaluator = Callable[["ProactiveEngine"], Sequence[ProactiveTrigger]]


class ProactiveEngine:
    """Ticked by `Scheduler` (or called directly); evaluates real
    system state via registered evaluators, and translates each
    resulting trigger into the appropriate, safe response -- never a
    shortcut around risk/approval, never a fabricated action.
    """

    def __init__(
        self,
        session_manager: SessionManager,
        audit_logger: AuditLogger,
        notifications: NotificationManager,
        *,
        act_callback: Optional[Callable[[ProactiveTrigger], None]] = None,
        extra_evaluators: Sequence[TriggerEvaluator] = (),
        clock: Callable[[], float] = time.time,
        stuck_suggest_seconds: float = _DEFAULT_STUCK_SUGGEST_SECONDS,
        stuck_alert_seconds: float = _DEFAULT_STUCK_ALERT_SECONDS,
        failure_observe_threshold: int = _DEFAULT_FAILURE_OBSERVE_THRESHOLD,
        failure_suggest_threshold: int = _DEFAULT_FAILURE_SUGGEST_THRESHOLD,
        max_act_triggers_per_evaluate: Optional[int] = 5,
    ) -> None:
        """`act_callback`, if given, is invoked for every ACT-level
        trigger -- the intended wiring is
        `lambda trigger: runtime.handle_event(trigger.description)`,
        left as an explicit injected callback (not a direct
        ExecutiveRuntime reference) so ProactiveEngine has no import-
        time dependency on runtime.py and stays independently testable.
        If omitted, ACT-level triggers are recorded via AuditLogger
        exactly like OBSERVE ones (a deliberate fail-safe: no callback
        wired means no autonomous action is possible, not a crash).
        """
        self._sessions = session_manager
        self._audit = audit_logger
        self._notifications = notifications
        self._act_callback = act_callback
        self._clock = clock
        self._stuck_suggest_seconds = stuck_suggest_seconds
        self._stuck_alert_seconds = stuck_alert_seconds
        self._failure_observe_threshold = failure_observe_threshold
        self._failure_suggest_threshold = failure_suggest_threshold
        # Directive D Part XV (ADR-0042): a real, previously-open
        # "runaway autonomous loop" gap -- evaluate() dispatched EVERY
        # ACT-level trigger from EVERY evaluator with no cap at all, so
        # a single evaluate() call (one Scheduler tick) could trigger
        # unboundedly many real handle_event() calls (real LLM cost)
        # if enough evaluators/triggers fired at once. Default of 5 is
        # a real, conservative ceiling per tick, not a magic number --
        # None restores the prior unbounded behavior explicitly, for a
        # caller that has its own reason to want that.
        self._max_act_triggers_per_evaluate = max_act_triggers_per_evaluate
        self._evaluators: Tuple[TriggerEvaluator, ...] = (
            ProactiveEngine._evaluate_stuck_tasks,
            ProactiveEngine._evaluate_repeated_delegation_failures,
        ) + tuple(extra_evaluators)

    def evaluate(self) -> Tuple[ProactiveTrigger, ...]:
        """Runs every evaluator against current real state, dispatches
        each resulting trigger per its action level, and returns the
        full set of triggers found (for callers/tests that want to
        inspect what happened this tick).

        Real resource guard (Directive D Part XV, ADR-0042): at most
        `max_act_triggers_per_evaluate` ACT-level triggers are actually
        dispatched (i.e. actually reach `act_callback` and therefore a
        real `handle_event()` call) per `evaluate()` call -- every
        trigger beyond that is recorded as throttled via the existing
        `AuditLogger`, not silently dropped, and non-ACT triggers
        (OBSERVE/SUGGEST/ASK/URGENTLY_ALERT) are never throttled, since
        those never themselves cause a real LLM call.
        """
        triggers: List[ProactiveTrigger] = []
        for evaluator in self._evaluators:
            triggers.extend(evaluator(self))
        act_dispatched = 0
        for trigger in triggers:
            if trigger.action_level == ACTION_ACT:
                if (
                    self._max_act_triggers_per_evaluate is not None
                    and act_dispatched >= self._max_act_triggers_per_evaluate
                ):
                    self._audit.record(
                        "layla.proactive.act_throttled",
                        {"trigger_id": trigger.id, "description": trigger.description, "source": trigger.source,
                         "max_act_triggers_per_evaluate": self._max_act_triggers_per_evaluate},
                        task_id=trigger.task_id,
                    )
                    continue
                act_dispatched += 1
            self._dispatch(trigger)
        return tuple(triggers)

    def _dispatch(self, trigger: ProactiveTrigger) -> None:
        if trigger.action_level == ACTION_IGNORE:
            return  # explicitly not even audited -- never spam, never accumulate noise
        if trigger.action_level == ACTION_OBSERVE:
            self._audit.record(
                "layla.proactive.observed",
                {"trigger_id": trigger.id, "description": trigger.description, "evidence": trigger.evidence,
                 "source": trigger.source},
                task_id=trigger.task_id,
            )
            return
        if trigger.action_level in (ACTION_SUGGEST, ACTION_ASK):
            self._notifications.notify(SEVERITY_ACTION_REQUIRED, trigger.description, source=trigger.source)
            self._audit.record(
                "layla.proactive.suggested",
                {"trigger_id": trigger.id, "description": trigger.description, "evidence": trigger.evidence,
                 "source": trigger.source, "action_level": trigger.action_level},
                task_id=trigger.task_id,
            )
            return
        if trigger.action_level == ACTION_URGENTLY_ALERT:
            self._notifications.notify(SEVERITY_CRITICAL, trigger.description, source=trigger.source)
            self._audit.record(
                "layla.proactive.alerted",
                {"trigger_id": trigger.id, "description": trigger.description, "evidence": trigger.evidence,
                 "source": trigger.source},
                task_id=trigger.task_id,
            )
            return
        if trigger.action_level == ACTION_ACT:
            self._audit.record(
                "layla.proactive.act_triggered",
                {"trigger_id": trigger.id, "description": trigger.description, "evidence": trigger.evidence,
                 "source": trigger.source, "callback_wired": self._act_callback is not None},
                task_id=trigger.task_id,
            )
            if self._act_callback is not None:
                self._act_callback(trigger)
            return
        raise ValueError(f"unknown action_level {trigger.action_level!r} -- expected one of {_ACTION_LEVELS}")

    # --- built-in evaluators, both computed from real recorded state -------

    def _evaluate_stuck_tasks(self) -> Tuple[ProactiveTrigger, ...]:
        """A task sitting in REQUIRES_HUMAN for a long time is real,
        directly observable evidence that a human hasn't seen or acted
        on it yet -- not a guess.
        """
        now = self._clock()
        triggers = []
        for task in self._sessions.list_incomplete():
            if task.state != REQUIRES_HUMAN or not task.history:
                continue
            last_transition_at = task.history[-1].at
            try:
                age_seconds = now - datetime.datetime.fromisoformat(last_transition_at).timestamp()
            except ValueError:
                continue
            if age_seconds >= self._stuck_alert_seconds:
                level = ACTION_URGENTLY_ALERT
            elif age_seconds >= self._stuck_suggest_seconds:
                level = ACTION_SUGGEST
            else:
                continue
            triggers.append(ProactiveTrigger(
                id=f"stuck:{task.id}", action_level=level,
                description=f"Task {task.id!r} has been blocked in REQUIRES_HUMAN for "
                            f"{age_seconds:.0f}s ({task.blocked_reason or 'no reason recorded'}).",
                evidence={"task_id": task.id, "age_seconds": age_seconds, "blocked_reason": task.blocked_reason},
                source="proactive.stuck_tasks", task_id=task.id,
            ))
        return tuple(triggers)

    def _evaluate_repeated_delegation_failures(self) -> Tuple[ProactiveTrigger, ...]:
        """Real audit-history counting -- the same trigger shape
        GENESIS's proactive_engine.py used (failure-streak detection),
        reimplemented from scratch against Layla's own real AuditLogger
        data, not GENESIS code.
        """
        triggers = []
        for task in self._sessions.list_incomplete():
            history = self._audit.history(task_id=task.id)
            failures = [r for r in history if r.event_type in ("layla.delegation.failed", "layla.delegation.timeout")]
            count = len(failures)
            if count >= self._failure_suggest_threshold:
                level = ACTION_SUGGEST
            elif count >= self._failure_observe_threshold:
                level = ACTION_OBSERVE
            else:
                continue
            triggers.append(ProactiveTrigger(
                id=f"failures:{task.id}", action_level=level,
                description=f"Task {task.id!r} has {count} failed/timed-out delegation(s) recorded.",
                evidence={"task_id": task.id, "failure_count": count,
                          "event_types": tuple(r.event_type for r in failures)},
                source="proactive.repeated_failures", task_id=task.id,
            ))
        return tuple(triggers)
