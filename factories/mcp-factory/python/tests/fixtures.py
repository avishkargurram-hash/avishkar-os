"""Shared test fixtures: a fake, network-free ProtocolAdapter -- mirrors
avishkar_router.MockProvider / agent-factory tests' _FakeAgent pattern.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from avishkar_integration import ProtocolAdapter, ToolContract, ToolExecutionRequest, ToolExecutionResult
from avishkar_integration.errors import ProtocolInvocationError


class FakeAdapter(ProtocolAdapter):
    protocol_name = "fake"

    def __init__(
        self,
        tools: Tuple[ToolContract, ...] = (),
        *,
        fail_identities: Tuple[str, ...] = (),
        responses: Optional[Dict[str, str]] = None,
        protocol_name: Optional[str] = None,
    ):
        # Only set the instance attribute when explicitly overridden, so
        # a subclass's own class-level protocol_name (e.g.
        # _UnhealthyAdapter in test_planner.py) isn't silently shadowed
        # by this constructor's default -- a single test file can still
        # exercise multiple protocol names (e.g. verifying
        # make_mcp_call_node really routes through "mcp") by passing
        # protocol_name explicitly.
        if protocol_name is not None:
            self.protocol_name = protocol_name
        self._tools = tools
        self._fail_identities = set(fail_identities)
        self._responses = responses or {}
        self.invocation_count = 0

    def discover_tools(self) -> Tuple[ToolContract, ...]:
        return self._tools

    def invoke(self, contract: ToolContract, request: ToolExecutionRequest) -> ToolExecutionResult:
        self.invocation_count += 1
        if contract.identity in self._fail_identities:
            raise ProtocolInvocationError(f"fake adapter configured to fail for '{contract.identity}'")
        return ToolExecutionResult(
            tool_identity=contract.identity,
            protocol=self.protocol_name,
            status="success",
            output=self._responses.get(contract.identity, "ok"),
            latency_ms=0.0,
            attempts=1,
        )


def make_contract(identity: str = "demo-tool", protocol: str = "fake", **overrides) -> ToolContract:
    defaults = dict(description="A demo tool.", input_schema={"type": "object"})
    defaults.update(overrides)
    return ToolContract(identity=identity, protocol=protocol, **defaults)
