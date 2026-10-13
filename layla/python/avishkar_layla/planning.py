"""Planner. See CONTRACT.md SS6.

A real, deterministic, keyword-matching planner (via
CapabilityResolver.infer_relevant) -- not a model call. Explicit
`requested_capabilities` always takes precedence when a caller already
knows which capabilities are needed (e.g. from a prior Layla turn or a
UI selection), matching Part IV's explicit "do not blindly invoke every
agent -- use capability matching."
"""

from __future__ import annotations

from typing import Optional, Sequence

from .capability_resolver import CapabilityResolver
from .errors import UnknownCapabilityError
from .risk import classify_risk
from .types import LaylaTask, Plan, PlanStep, new_id


class Planner:
    def __init__(
        self,
        capability_resolver: CapabilityResolver,
        *,
        default_timeout_seconds: float = 30.0,
        default_max_attempts: int = 1,
    ) -> None:
        self._resolver = capability_resolver
        self._default_timeout_seconds = default_timeout_seconds
        self._default_max_attempts = default_max_attempts

    def plan(self, task: LaylaTask, *, requested_capabilities: Optional[Sequence[str]] = None) -> Plan:
        capabilities = (
            list(requested_capabilities)
            if requested_capabilities is not None
            else list(self._resolver.infer_relevant(task.input))
        )
        if not capabilities:
            raise UnknownCapabilityError(
                f"could not infer any capability for task {task.id!r} from its input; "
                f"pass requested_capabilities explicitly if this is expected"
            )
        risk = classify_risk(task.input)
        steps = tuple(
            PlanStep(
                id=new_id("step"),
                required_capability=capability,
                input=task.input,
                risk_level=risk,
                timeout_seconds=self._default_timeout_seconds,
                max_attempts=self._default_max_attempts,
            )
            for capability in capabilities
        )
        return Plan(id=new_id("plan"), task_id=task.id, steps=steps)
