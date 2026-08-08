"""MCPAdapter -- the first-class ProtocolAdapter, built on the official
`mcp` Python SDK (lazily imported -- see __init__). Speaks the MCP stdio
transport by default.

`session_provider` is the dependency-injection seam tests use to supply
a fake session without a live subprocess/server, mirroring
router.providers.anthropic_provider.AnthropicProvider's `client=` seam.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Any, Callable, Optional, Tuple

from ..errors import ProtocolInvocationError
from ..protocol import ProtocolAdapter
from ..types import AuditInfo, RetryPolicy, ToolContract, ToolExecutionRequest, ToolExecutionResult


class MCPAdapter(ProtocolAdapter):
    protocol_name = "mcp"

    def __init__(
        self,
        server: Optional[Any] = None,  # mcp.client.stdio.StdioServerParameters
        *,
        session_provider: Optional[Callable[[], Any]] = None,
        default_timeout_seconds: float = 30.0,
        server_name: str = "unknown",
    ) -> None:
        self._default_timeout = default_timeout_seconds
        self._server_name = server_name
        if session_provider is not None:
            self._session_provider = session_provider
            return
        try:
            import mcp  # noqa: F401 -- import-time dependency check
        except ImportError as exc:
            raise ImportError(
                "MCPAdapter requires the 'mcp' package. Install it with 'pip install mcp' "
                "or the 'avishkar-integration[mcp]' extra."
            ) from exc
        if server is None:
            raise ValueError(
                "server (mcp.client.stdio.StdioServerParameters) is required unless session_provider is injected"
            )
        self._server = server
        self._session_provider = self._default_session

    @asynccontextmanager
    async def _default_session(self):
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client

        async with stdio_client(self._server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    # --- discovery -----------------------------------------------------

    def discover_tools(self) -> Tuple[ToolContract, ...]:
        return asyncio.run(self._discover_tools_async())

    async def _discover_tools_async(self) -> Tuple[ToolContract, ...]:
        try:
            async with self._session_provider() as session:
                result = await session.list_tools()
        except Exception as exc:  # noqa: BLE001 -- normalized into our own hierarchy
            raise ProtocolInvocationError(f"MCP list_tools failed: {exc}") from exc
        return tuple(self._to_contract(tool) for tool in result.tools)

    def _to_contract(self, tool: Any) -> ToolContract:
        return ToolContract(
            identity=tool.name,
            description=tool.description or "",
            protocol=self.protocol_name,
            input_schema=tool.input_schema or {},
            output_schema=getattr(tool, "output_schema", None),
            timeout_seconds=self._default_timeout,
            retry_policy=RetryPolicy(max_attempts=1),
            auth_requirement="mcp_session",
            audit=AuditInfo(created_by="mcp-discovery"),
            protocol_config={"server_name": self._server_name},
        )

    # --- invocation ------------------------------------------------------

    def invoke(self, contract: ToolContract, request: ToolExecutionRequest) -> ToolExecutionResult:
        return asyncio.run(self._invoke_async(contract, request))

    async def _invoke_async(self, contract: ToolContract, request: ToolExecutionRequest) -> ToolExecutionResult:
        start = time.monotonic()
        try:
            async with self._session_provider() as session:
                result = await session.call_tool(contract.identity, request.input)
        except Exception as exc:  # noqa: BLE001 -- normalized into our own hierarchy
            raise ProtocolInvocationError(f"MCP call_tool('{contract.identity}') failed: {exc}") from exc

        elapsed_ms = (time.monotonic() - start) * 1000
        is_error = bool(getattr(result, "is_error", False))
        output_text = "".join(
            block.text for block in getattr(result, "content", []) if getattr(block, "type", None) == "text"
        )
        return ToolExecutionResult(
            tool_identity=contract.identity,
            protocol=self.protocol_name,
            status="error" if is_error else "success",
            output=None if is_error else output_text,
            error=output_text if is_error else None,
            latency_ms=elapsed_ms,
            attempts=1,
        )

    def health_check(self) -> str:
        try:
            asyncio.run(self._discover_tools_async())
            return "healthy"
        except Exception:  # noqa: BLE001 -- health check must never raise
            return "unhealthy"
