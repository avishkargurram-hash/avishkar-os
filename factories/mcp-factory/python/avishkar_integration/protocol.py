"""ProtocolAdapter -- the Protocol Abstraction Layer. See CONTRACT.md SS2.

Any protocol -- MCP, REST, GraphQL, a Python SDK, a CLI, a database, a
filesystem, a webhook receiver, or a protocol that doesn't exist yet --
implements exactly this interface. Every consumer in this framework
depends on ProtocolAdapter, never on a concrete adapter class.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Tuple

from .types import ToolContract, ToolExecutionRequest, ToolExecutionResult


class ProtocolAdapter(ABC):
    #: Stable identifier, e.g. "mcp", "rest". Set by each concrete subclass.
    protocol_name: str

    @abstractmethod
    def discover_tools(self) -> Tuple[ToolContract, ...]:
        """Every tool this adapter can currently expose."""

    @abstractmethod
    def invoke(self, contract: ToolContract, request: ToolExecutionRequest) -> ToolExecutionResult:
        """Execute one tool call. Raises ProtocolInvocationError (never
        this adapter's own vendor-specific exception type) on transport
        failure -- ToolRuntime is responsible for turning that into a
        ToolExecutionResult(status="error", ...).
        """

    def health_check(self) -> str:
        """Default implementation: a successful discover_tools() means
        "healthy". Adapters with a cheaper health signal (e.g. a ping
        endpoint) should override this.
        """
        try:
            self.discover_tools()
            return "healthy"
        except Exception:  # noqa: BLE001 -- health check must never raise
            return "unhealthy"
