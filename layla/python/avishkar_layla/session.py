"""SessionManager -- durable, restart-safe LaylaTask state. See
CONTRACT.md SS10.

Persisted through the same LaylaMemoryPolicy every other Layla
component uses, under kind="long_term" with keys namespaced
session:{task.id}. A separate index key (session:__index__) holds the
known task ids, since MemoryPolicy's locked interface has no key
enumeration method (see CONTRACT.md SS10 for why).
"""

from __future__ import annotations

import dataclasses
import threading
from typing import Optional, Tuple

from .memory_policy import LaylaMemoryPolicy
from .types import TERMINAL_STATES, LaylaTask, Plan, PlanStep, StateTransition

_KIND = "long_term"
_INDEX_KEY = "session:__index__"


def _plan_to_dict(plan: Optional[Plan]) -> Optional[dict]:
    if plan is None:
        return None
    return {
        "id": plan.id,
        "task_id": plan.task_id,
        "steps": [dataclasses.asdict(s) for s in plan.steps],
    }


def _plan_from_dict(data: Optional[dict]) -> Optional[Plan]:
    if data is None:
        return None
    return Plan(
        id=data["id"], task_id=data["task_id"],
        steps=tuple(PlanStep(**s) for s in data["steps"]),
    )


def _task_to_dict(task: LaylaTask) -> dict:
    return {
        "input": task.input,
        "id": task.id,
        "state": task.state,
        "history": [dataclasses.asdict(h) for h in task.history],
        "context": dict(task.context),
        "plan_id": task.plan_id,
        "result": task.result,
        "blocked_reason": task.blocked_reason,
        "principal_id": task.principal_id,
        "plan": _plan_to_dict(task.plan),
        "pending_approval_id": task.pending_approval_id,
    }


def _task_from_dict(data: dict) -> LaylaTask:
    return LaylaTask(
        input=data["input"],
        id=data["id"],
        state=data["state"],
        history=tuple(StateTransition(**h) for h in data["history"]),
        context=data.get("context", {}),
        plan_id=data.get("plan_id"),
        result=data.get("result"),
        blocked_reason=data.get("blocked_reason"),
        principal_id=data.get("principal_id"),
        plan=_plan_from_dict(data.get("plan")),
        pending_approval_id=data.get("pending_approval_id"),
    )


class SessionManager:
    def __init__(self, memory: LaylaMemoryPolicy) -> None:
        self._memory = memory
        # Priority 17.4 (ADR-0024): guards the index's read-modify-write
        # (recall existing ids, add this one, write back) -- two
        # concurrent save() calls for DIFFERENT tasks would otherwise
        # race on the shared __index__ record and could lose one task's
        # id from it (a classic lost-update).
        self._lock = threading.Lock()

    def save(self, task: LaylaTask) -> None:
        self._memory.remember(
            _KIND, f"session:{task.id}", _task_to_dict(task),
            provenance="session-manager", importance="high",
        )
        with self._lock:
            index_record = self._memory.recall(_KIND, _INDEX_KEY)
            ids = set(index_record.value) if index_record else set()
            ids.add(task.id)
            self._memory.remember(_KIND, _INDEX_KEY, sorted(ids), provenance="session-manager")

    def load(self, task_id: str) -> Optional[LaylaTask]:
        record = self._memory.recall(_KIND, f"session:{task_id}")
        return _task_from_dict(record.value) if record else None

    def list_incomplete(self) -> Tuple[LaylaTask, ...]:
        """Every persisted task not in a terminal state -- what a
        process restart should resume. See CONTRACT.md SS10.
        """
        index_record = self._memory.recall(_KIND, _INDEX_KEY)
        if index_record is None:
            return ()
        tasks = (self.load(task_id) for task_id in index_record.value)
        return tuple(t for t in tasks if t is not None and t.state not in TERMINAL_STATES)

    def list_all(self) -> Tuple[LaylaTask, ...]:
        """Every persisted task regardless of state (Mission Layla Part
        3, PredictionEngine) -- the same index this class already
        maintains, without `list_incomplete()`'s terminal-state filter.
        Additive: nothing about list_incomplete()'s own behavior changes.
        """
        index_record = self._memory.recall(_KIND, _INDEX_KEY)
        if index_record is None:
            return ()
        tasks = (self.load(task_id) for task_id in index_record.value)
        return tuple(t for t in tasks if t is not None)
