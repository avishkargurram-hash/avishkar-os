"""Tests for MCPAdapter.

Uses the `session_provider` injection seam (see adapters/mcp_adapter.py)
with a fake async session, so these tests exercise the real translation
logic (Tool -> ToolContract, CallToolResult -> ToolExecutionResult, error
normalization) without a live MCP server or subprocess -- mirroring
router's test_anthropic_provider.py pattern.
"""

import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace

from avishkar_integration.adapters.mcp_adapter import MCPAdapter
from avishkar_integration.errors import ProtocolInvocationError
from avishkar_integration.types import ToolContract, ToolExecutionRequest


class _FakeSession:
    def __init__(self, tools=(), call_result=None, raise_on_call=None, raise_on_list=None):
        self._tools = tools
        self._call_result = call_result
        self._raise_on_call = raise_on_call
        self._raise_on_list = raise_on_list
        self.called_with = None

    async def list_tools(self):
        if self._raise_on_list:
            raise self._raise_on_list
        return SimpleNamespace(tools=self._tools)

    async def call_tool(self, name, arguments):
        self.called_with = (name, arguments)
        if self._raise_on_call:
            raise self._raise_on_call
        return self._call_result


def _provider_for(session: _FakeSession):
    @asynccontextmanager
    async def _provide():
        yield session

    return _provide


def _fake_tool(name="get_weather", description="Get weather", input_schema=None):
    return SimpleNamespace(name=name, description=description, input_schema=input_schema or {"type": "object"}, output_schema=None)


class TestMCPAdapterDiscovery(unittest.TestCase):
    def test_discover_tools_maps_mcp_tool_to_contract(self):
        session = _FakeSession(tools=(_fake_tool(),))
        adapter = MCPAdapter(session_provider=_provider_for(session), server_name="github")

        contracts = adapter.discover_tools()

        self.assertEqual(len(contracts), 1)
        self.assertEqual(contracts[0].identity, "get_weather")
        self.assertEqual(contracts[0].protocol, "mcp")
        self.assertEqual(contracts[0].protocol_config["server_name"], "github")
        self.assertEqual(contracts[0].auth_requirement, "mcp_session")

    def test_discover_tools_transport_failure_normalized(self):
        session = _FakeSession(raise_on_list=RuntimeError("connection reset"))
        adapter = MCPAdapter(session_provider=_provider_for(session))

        with self.assertRaises(ProtocolInvocationError):
            adapter.discover_tools()


class TestMCPAdapterInvoke(unittest.TestCase):
    def test_successful_call_extracts_text_content(self):
        result = SimpleNamespace(
            is_error=False, content=[SimpleNamespace(type="text", text="72F and sunny")]
        )
        session = _FakeSession(call_result=result)
        adapter = MCPAdapter(session_provider=_provider_for(session))
        contract = ToolContract(identity="get_weather", description="Get weather", protocol="mcp", input_schema={})

        outcome = adapter.invoke(contract, ToolExecutionRequest(input={"city": "Paris"}))

        self.assertEqual(outcome.status, "success")
        self.assertEqual(outcome.output, "72F and sunny")
        self.assertEqual(session.called_with, ("get_weather", {"city": "Paris"}))

    def test_tool_reported_error_maps_to_error_status(self):
        result = SimpleNamespace(is_error=True, content=[SimpleNamespace(type="text", text="city not found")])
        session = _FakeSession(call_result=result)
        adapter = MCPAdapter(session_provider=_provider_for(session))
        contract = ToolContract(identity="get_weather", description="Get weather", protocol="mcp", input_schema={})

        outcome = adapter.invoke(contract, ToolExecutionRequest(input={}))

        self.assertEqual(outcome.status, "error")
        self.assertEqual(outcome.error, "city not found")

    def test_transport_failure_raises_protocol_invocation_error(self):
        session = _FakeSession(raise_on_call=RuntimeError("subprocess died"))
        adapter = MCPAdapter(session_provider=_provider_for(session))
        contract = ToolContract(identity="get_weather", description="Get weather", protocol="mcp", input_schema={})

        with self.assertRaises(ProtocolInvocationError):
            adapter.invoke(contract, ToolExecutionRequest(input={}))


class TestMCPAdapterHealthCheck(unittest.TestCase):
    def test_healthy_when_discovery_succeeds(self):
        session = _FakeSession(tools=(_fake_tool(),))
        adapter = MCPAdapter(session_provider=_provider_for(session))
        self.assertEqual(adapter.health_check(), "healthy")

    def test_unhealthy_when_discovery_fails(self):
        session = _FakeSession(raise_on_list=RuntimeError("down"))
        adapter = MCPAdapter(session_provider=_provider_for(session))
        self.assertEqual(adapter.health_check(), "unhealthy")


class TestMCPAdapterConstruction(unittest.TestCase):
    def test_requires_server_or_session_provider(self):
        # mcp IS installed in this environment (dev dependency), so the
        # ImportError path isn't exercised here -- this asserts the
        # complementary contract: no session_provider AND no server is
        # a caller error, not a silent default.
        with self.assertRaises(ValueError):
            MCPAdapter()


if __name__ == "__main__":
    unittest.main()
