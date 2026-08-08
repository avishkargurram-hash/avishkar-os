"""IntegrationPlanner -- AI Router Integration: selecting the best tool,
protocol, and (via the already-built AI Router) model for a requested
capability. See CONTRACT.md SS6.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from .errors import NoMatchingToolError
from .registry import UniversalToolRegistry
from .types import ToolContract


@dataclasses.dataclass(frozen=True)
class ExecutionPlan:
    tool_contract: ToolContract
    model_id: Optional[str]
    rationale: str


class IntegrationPlanner:
    """"Best tool / best protocol / best execution path" resolves to: pick
    a healthy matching ToolContract over an unhealthy one when both
    exist. "Best model" is explicitly delegated to the already-built AI
    Router (Phase 2) via the optional `router` -- not reinvented here.
    """

    def __init__(self, registry: UniversalToolRegistry, router=None) -> None:
        self._registry = registry
        self._router = router

    def plan(self, capability: str, *, task_type: Optional[str] = None) -> ExecutionPlan:
        candidates = self._registry.find_by_capability(capability)
        if not candidates:
            raise NoMatchingToolError(f"No registered tool matches capability '{capability}'")

        healthy = [
            c for c in candidates
            if self._registry.get_health(c.protocol, c.identity) in ("healthy", "unknown")
        ]
        chosen = healthy[0] if healthy else candidates[0]
        health_note = "healthy/unknown" if chosen in healthy else "unhealthy, no healthier alternative registered"

        model_id = None
        if self._router is not None and task_type is not None:
            models = [m for m in self._router.list_models() if task_type in m.capabilities]
            if models:
                model_id = models[0].model_id

        rationale = (
            f"selected '{chosen.qualified_name}' matching capability '{capability}' "
            f"({health_note}); {len(candidates)} candidate(s) considered"
        )
        return ExecutionPlan(tool_contract=chosen, model_id=model_id, rationale=rationale)
