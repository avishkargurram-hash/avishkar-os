"""Explicit LaylaTask state machine. See CONTRACT.md SS1.

A fixed adjacency table, not an "anything can go anywhere" machine --
every transition Layla's runtime performs is checked against this
table and rejected otherwise.
"""

from __future__ import annotations

import datetime

from .errors import InvalidTransitionError
from .types import (
    APPROVAL_PENDING,
    BLOCKED,
    CANCELLED,
    COMPLETED,
    CONTEXT_LOADING,
    DELEGATING,
    EXECUTING,
    FAILED,
    PLANNING,
    RECEIVED,
    REQUIRES_HUMAN,
    SYNTHESIZING,
    TERMINAL_STATES,
    TIMEOUT,
    UNDERSTANDING,
    VERIFYING,
    WAITING,
    LaylaTask,
    StateTransition,
)

# Exception states reachable from any non-terminal state -- listed once,
# applied to every "normal path" state below rather than repeated per row.
_EXCEPTION_STATES = (FAILED, CANCELLED, TIMEOUT, BLOCKED, REQUIRES_HUMAN)

ALLOWED_TRANSITIONS = {
    RECEIVED: (UNDERSTANDING,) + _EXCEPTION_STATES,
    UNDERSTANDING: (CONTEXT_LOADING,) + _EXCEPTION_STATES,
    # SYNTHESIZING added here for Phase 2 (Mission Layla, intent-first
    # orchestration): a task whose intent doesn't require action is
    # answered conversationally and skips Planner entirely -- see
    # runtime.py's CONTEXT_LOADING block. PLANNING stays the default
    # path for every existing caller; this only adds a second option.
    CONTEXT_LOADING: (PLANNING, SYNTHESIZING) + _EXCEPTION_STATES,
    PLANNING: (APPROVAL_PENDING, EXECUTING) + _EXCEPTION_STATES,
    APPROVAL_PENDING: (EXECUTING,) + _EXCEPTION_STATES,
    EXECUTING: (DELEGATING, VERIFYING) + _EXCEPTION_STATES,
    DELEGATING: (WAITING, VERIFYING) + _EXCEPTION_STATES,
    WAITING: (VERIFYING,) + _EXCEPTION_STATES,
    VERIFYING: (SYNTHESIZING,) + _EXCEPTION_STATES,
    SYNTHESIZING: (COMPLETED,) + _EXCEPTION_STATES,
    # Terminal and REQUIRES_HUMAN states have no outgoing transitions of
    # their own here -- REQUIRES_HUMAN is resumed by constructing a new
    # transition explicitly from application code (e.g. back to
    # EXECUTING once a human responds), which is still checked against
    # this table; it isn't a dead end by omission, it just isn't a
    # traversal this table drives automatically.
    REQUIRES_HUMAN: (EXECUTING, PLANNING) + _EXCEPTION_STATES,
}


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class StateMachine:
    """Validates and applies LaylaTask state transitions. See CONTRACT.md SS1."""

    def transition(self, task: LaylaTask, new_state: str) -> LaylaTask:
        if task.state in TERMINAL_STATES:
            raise InvalidTransitionError(
                f"task {task.id!r} is in terminal state {task.state!r}; no further transitions allowed"
            )
        allowed = ALLOWED_TRANSITIONS.get(task.state, ())
        if new_state not in allowed:
            raise InvalidTransitionError(
                f"task {task.id!r} cannot transition {task.state!r} -> {new_state!r}; "
                f"allowed from {task.state!r}: {allowed}"
            )
        record = StateTransition(from_state=task.state, to_state=new_state, at=_now())
        task.history = task.history + (record,)
        task.state = new_state
        return task

    def is_terminal(self, task: LaylaTask) -> bool:
        return task.state in TERMINAL_STATES
