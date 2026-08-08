"""Core data types for the Agent Framework. See CONTRACT.md SS1."""

from __future__ import annotations

import dataclasses
from typing import Any, Mapping, Optional, Tuple


@dataclasses.dataclass(frozen=True)
class Task:
    """A unit of work given to a ChiefDomainAgent or Orchestrator."""

    input: str
    context: Mapping[str, Any] = dataclasses.field(default_factory=dict)
    task_type: Optional[str] = None
    metadata: Mapping[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class ThinkingStep:
    """One plan/act/reflect step in an agent's reasoning trace."""

    strategy: str
    content: str


@dataclasses.dataclass(frozen=True)
class ToolCallRecord:
    """What was actually invoked during a task, in order."""

    tool_name: str
    input: Any
    output: Any = None
    error: Optional[str] = None


@dataclasses.dataclass(frozen=True)
class AgentResult:
    """Returned by ChiefDomainAgent.handle() and Orchestrator.route()."""

    output: str
    agent_name: str
    thinking_trace: Tuple[ThinkingStep, ...]
    tool_calls: Tuple[ToolCallRecord, ...]
    iterations: int
    status: str  # "completed" | "blocked" | "failed"
    cost_usd: float
    blocked_reason: Optional[str] = None
