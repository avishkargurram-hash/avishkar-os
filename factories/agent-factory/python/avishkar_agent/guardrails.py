"""Guardrail, QualityGate, and ApprovalGate -- the pre-execution,
post-execution, and human-in-the-loop control points of the reasoning
loop. See CONTRACT.md SS6 and SS17-SS19 of the agent template.
"""

from __future__ import annotations

import dataclasses
from typing import Callable, Optional

from .types import AgentResult, Task


@dataclasses.dataclass(frozen=True)
class Guardrail:
    """A pre-execution check (SS18 of the agent template). `check`
    returns None to allow the task through, or a block reason string to
    stop it before any model or tool call happens.
    """

    name: str
    check: Callable[[Task], Optional[str]]


@dataclasses.dataclass(frozen=True)
class QualityGate:
    """A post-execution check (SS19). `check` returns True if the
    candidate result meets the bar. A failing gate either triggers
    another reasoning iteration (if budget remains) or marks the final
    result "failed" -- see agent.py.
    """

    name: str
    check: Callable[[AgentResult], bool]


@dataclasses.dataclass
class ApprovalGate:
    """Human-in-the-loop approval (SS7/SS18). Mirrors the
    always_allow / always_ask permission-policy pattern used elsewhere
    in the industry for agent tool confirmation.

    `callback`, when policy is "always_ask", is called with the task and
    must return True (allow) or False (deny). In an interactive product
    this is wired to an actual human prompt; in tests and automation it's
    a fixed function.
    """

    policy: str = "always_allow"  # "always_allow" | "always_ask"
    callback: Optional[Callable[[Task], bool]] = None

    def __post_init__(self) -> None:
        if self.policy not in ("always_allow", "always_ask"):
            raise ValueError(f"ApprovalGate.policy must be 'always_allow' or 'always_ask', got {self.policy!r}")
        if self.policy == "always_ask" and self.callback is None:
            raise ValueError("ApprovalGate.policy='always_ask' requires a callback")

    def evaluate(self, task: Task) -> bool:
        if self.policy == "always_allow":
            return True
        assert self.callback is not None  # enforced in __post_init__
        return self.callback(task)
