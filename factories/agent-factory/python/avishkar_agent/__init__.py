"""avishkar_agent -- Python reference implementation of the Agent Framework.

See ../CONTRACT.md for the language-agnostic contract this package
implements, and ../README.md for the framework's full documentation
(Vision, Architecture, Extension Model, Best Practices, Anti-Patterns).

Per DECISIONS.md ADR-0010: a Chief Domain Agent built on this framework
is a complete software system (blueprint + domain module wiring real
tools/guardrails/quality gates), never a bare system prompt.
"""

from .agent import ChiefDomainAgent
from .blueprint import AgentBlueprint, BlueprintToolRef, MemoryPolicyConfig
from .errors import (
    AgentFrameworkError,
    DuplicateAgentError,
    GuardrailBlockedError,
    InvalidBlueprintError,
    MCPServerNotAvailableError,
    NoMatchingAgentError,
    ToolNotFoundError,
    UnknownAgentError,
)
from .generator import scaffold_agent
from .guardrails import ApprovalGate, Guardrail, QualityGate
from .memory import InMemoryMemoryPolicy, MemoryPolicy
from .orchestrator import Orchestrator
from .thinking import DEFAULT_THINKING_MODELS, ThinkingModel
from .tools import MCPToolRef, Tool, ToolRegistry
from .types import AgentResult, Task, ThinkingStep, ToolCallRecord

__version__ = "0.1.0"

__all__ = [
    "ChiefDomainAgent",
    "Orchestrator",
    "AgentBlueprint",
    "BlueprintToolRef",
    "MemoryPolicyConfig",
    "MemoryPolicy",
    "InMemoryMemoryPolicy",
    "ToolRegistry",
    "Tool",
    "MCPToolRef",
    "ThinkingModel",
    "DEFAULT_THINKING_MODELS",
    "Guardrail",
    "QualityGate",
    "ApprovalGate",
    "Task",
    "ThinkingStep",
    "ToolCallRecord",
    "AgentResult",
    "scaffold_agent",
    "AgentFrameworkError",
    "InvalidBlueprintError",
    "ToolNotFoundError",
    "MCPServerNotAvailableError",
    "GuardrailBlockedError",
    "NoMatchingAgentError",
    "UnknownAgentError",
    "DuplicateAgentError",
    "__version__",
]
