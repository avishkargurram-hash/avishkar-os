"""Error types for the Agent Framework. See CONTRACT.md."""

from __future__ import annotations


class AgentFrameworkError(Exception):
    """Base class for every error avishkar_agent raises."""


class InvalidBlueprintError(AgentFrameworkError):
    """An AgentBlueprint failed validation (see blueprint.py)."""


class ToolNotFoundError(AgentFrameworkError):
    """ToolRegistry.call() named a tool that was never registered."""


class MCPServerNotAvailableError(AgentFrameworkError):
    """An MCPToolRef was called before its `mcp/<server>` exists.

    A clear, typed failure -- not a crash, not a silent no-op. Phase 4
    (mcp-factory) is what makes these resolvable.
    """


class GuardrailBlockedError(AgentFrameworkError):
    """Raised internally when a guardrail blocks a task; ChiefDomainAgent
    catches this and returns a "blocked" AgentResult rather than letting
    it propagate -- callers should not need to catch this directly.
    """


class NoMatchingAgentError(AgentFrameworkError):
    """Orchestrator.route() found no registered agent matching the task."""


class UnknownAgentError(AgentFrameworkError):
    """Orchestrator.delegate_team()/broadcast() named an agent that isn't
    registered with this Orchestrator.
    """


class DuplicateAgentError(AgentFrameworkError):
    """Two agents passed to one Orchestrator share a name -- refused at
    construction time rather than silently picking one (mirrors
    router.DuplicateModelError).
    """
