"""Core data types for the AI Router Framework. See CONTRACT.md SS1.

All types are frozen dataclasses -- values passed between Router,
RoutingPolicy, and ModelProvider are treated as immutable records, not
mutable state shared across calls.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Mapping, Optional, Tuple


@dataclasses.dataclass(frozen=True)
class Message:
    """One turn in a CompletionRequest. Text-only in v1 -- see
    CONTRACT.md SS1 and README.md Limitations for multi-modal content.

    Phase 1 (Layla redesign): tool_calls/tool_call_id added, additive with
    empty/None defaults -- every existing text-only caller is unaffected.
    """

    role: str  # "user" | "assistant" | "system" | "tool"
    content: str
    tool_calls: Tuple[Mapping[str, Any], ...] = ()  # assistant-issued tool calls (OpenAI tool_calls shape)
    tool_call_id: Optional[str] = None              # for role="tool": which call this message answers


@dataclasses.dataclass(frozen=True)
class ModelSpec:
    """What a ModelProvider publishes about one model it can serve."""

    model_id: str
    provider: str
    capabilities: Tuple[str, ...]
    input_cost_per_mtok: float
    output_cost_per_mtok: float
    max_context_tokens: int
    max_output_tokens: int


@dataclasses.dataclass(frozen=True)
class CompletionRequest:
    """A request to Router.route(). See CONTRACT.md SS1 for field
    semantics, including why `model` set explicitly skips fallback.
    """

    messages: Tuple[Message, ...]
    model: Optional[str] = None
    capabilities: Tuple[str, ...] = ()
    task_type: Optional[str] = None
    max_tokens: int = 1024
    metadata: Mapping[str, Any] = dataclasses.field(default_factory=dict)
    # Phase 1 (Layla redesign): OpenAI tool-schema dicts + tool_choice.
    # Additive -- empty/None defaults mean every existing text-only caller
    # is byte-identical in the request it sends.
    tools: Tuple[Mapping[str, Any], ...] = ()
    tool_choice: Optional[Any] = None


@dataclasses.dataclass(frozen=True)
class ProviderResponse:
    """Returned by ModelProvider.complete(). The Router wraps this into a
    CompletionResponse, adding cost/latency/model/provider bookkeeping the
    provider adapter itself doesn't need to know about.
    """

    content: str
    input_tokens: int
    output_tokens: int
    stop_reason: Optional[str] = None
    raw: Any = None
    # Priority 17.5 (ADR-0025): the provider's own request/message id,
    # when the provider surfaces one (AnthropicProvider populates this
    # from the real API response's `.id`; MockProvider leaves it None --
    # a mock response has no real request to identify). Optional and
    # additive -- every existing ModelProvider/test that never sets it
    # is unaffected.
    request_id: Optional[str] = None
    tool_calls: Tuple[Mapping[str, Any], ...] = ()  # Phase 1 -- see Message.tool_calls


@dataclasses.dataclass(frozen=True)
class CompletionResponse:
    """Returned by Router.route()."""

    content: str
    model_used: str
    provider_used: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    stop_reason: Optional[str] = None
    request_id: Optional[str] = None  # Priority 17.5 -- see ProviderResponse.request_id
    tool_calls: Tuple[Mapping[str, Any], ...] = ()  # Phase 1 -- see Message.tool_calls
