"""Core data types for the Universal Integration Framework.
See CONTRACT.md SS1.

Design choice, stated explicitly (also in CONTRACT.md): live/mutable
state (health, metrics, invocation audit log) is deliberately kept OFF
ToolContract. A contract is a frozen declaration; live state lives in the
registry and runtime -- the same split router/types.py makes between
ModelSpec (static) and CostTracker (live).
"""

from __future__ import annotations

import dataclasses
from typing import Any, Mapping, Optional, Tuple


@dataclasses.dataclass(frozen=True)
class RateLimit:
    requests_per_minute: int


@dataclasses.dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    backoff_seconds: float = 0.0


@dataclasses.dataclass(frozen=True)
class AuditInfo:
    created_by: str = "unknown"
    created_at: str = ""


@dataclasses.dataclass(frozen=True)
class ToolContract:
    """The universal, protocol-independent tool contract every
    ProtocolAdapter publishes. See CONTRACT.md SS1.
    """

    identity: str
    description: str
    protocol: str
    input_schema: Mapping[str, Any]
    output_schema: Optional[Mapping[str, Any]] = None
    permissions: Tuple[str, ...] = ()
    auth_requirement: str = "none"
    rate_limit: Optional[RateLimit] = None
    timeout_seconds: float = 30.0
    retry_policy: RetryPolicy = dataclasses.field(default_factory=RetryPolicy)
    error_handling: str = "return_error_result"  # | "raise"
    version: str = "1.0.0"
    health_status: str = "unknown"  # declared default -- see module docstring
    audit: AuditInfo = dataclasses.field(default_factory=AuditInfo)
    protocol_config: Mapping[str, Any] = dataclasses.field(default_factory=dict)

    @property
    def qualified_name(self) -> str:
        return f"{self.protocol}:{self.identity}"


@dataclasses.dataclass(frozen=True)
class ToolExecutionRequest:
    input: Any
    caller: Optional[str] = None
    metadata: Mapping[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class ToolExecutionResult:
    tool_identity: str
    protocol: str
    status: str  # "success" | "error" | "timeout" | "denied"
    output: Any = None
    error: Optional[str] = None
    latency_ms: float = 0.0
    attempts: int = 1
