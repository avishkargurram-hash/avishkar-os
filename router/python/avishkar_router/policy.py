"""RoutingPolicy -- candidate model selection. See CONTRACT.md SS3.

A policy is a pure function of (rules, default_model) -> candidate list.
It has no knowledge of providers, cost, or network state -- that
separation is what makes it trivially unit-testable and reusable across
Router instances.
"""

from __future__ import annotations

import dataclasses
from typing import Optional, Tuple

from .types import CompletionRequest


@dataclasses.dataclass(frozen=True)
class RoutingRule:
    """One entry in a RoutingPolicy. Matches a request if `task_type`
    (when set) equals the request's, and `capabilities` is a subset of
    the request's declared capabilities. `models` is the ordered
    candidate list tried when this rule matches.
    """

    models: Tuple[str, ...]
    capabilities: Tuple[str, ...] = ()
    task_type: Optional[str] = None

    def matches(self, request: CompletionRequest) -> bool:
        if self.task_type is not None and request.task_type != self.task_type:
            return False
        if not set(self.capabilities).issubset(set(request.capabilities)):
            return False
        return True


@dataclasses.dataclass(frozen=True)
class RoutingPolicy:
    """Selects, for a given CompletionRequest, the ordered list of
    model_ids the Router should try. See CONTRACT.md SS3 for the full
    selection algorithm and why an explicit `request.model` skips
    fallback entirely.
    """

    default_model: str
    rules: Tuple[RoutingRule, ...] = ()

    def select_candidates(self, request: CompletionRequest) -> Tuple[str, ...]:
        if request.model:
            return (request.model,)
        for rule in self.rules:
            if rule.matches(request):
                return rule.models
        return (self.default_model,)

    @classmethod
    def from_config(cls, config) -> "RoutingPolicy":  # config: avishkar_core.Config
        """Build a RoutingPolicy from a Core Engine Config document under
        the 'router' key, e.g.:

            router:
              default_model: claude-opus-5
              rules:
                - task_type: cheap
                  models: [claude-haiku-4-5, claude-sonnet-5]
                - capabilities: [vision]
                  models: [claude-opus-5]
        """
        default_model = config.require("router.default_model")
        raw_rules = config.get("router.rules", ())
        rules = tuple(
            RoutingRule(
                models=tuple(rule["models"]),
                capabilities=tuple(rule.get("capabilities", ())),
                task_type=rule.get("task_type"),
            )
            for rule in raw_rules
        )
        return cls(default_model=default_model, rules=rules)
