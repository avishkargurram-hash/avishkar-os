import unittest

from avishkar_agent import MCPToolRef

from avishkar_integration import NoMatchingToolError, ToolNotFoundError, UniversalToolRegistry, request_capability, resolve_mcp_tool_ref

from fixtures import make_contract


class TestResolveMcpToolRef(unittest.TestCase):
    def test_resolves_registered_tool(self):
        registry = UniversalToolRegistry()
        registry.register_tool(make_contract("create_pull_request", protocol="mcp"))
        ref = MCPToolRef(server="github", tool_name="create_pull_request")

        contract = resolve_mcp_tool_ref(ref, registry)

        self.assertEqual(contract.identity, "create_pull_request")
        self.assertEqual(contract.protocol, "mcp")

    def test_unresolved_ref_raises_tool_not_found(self):
        registry = UniversalToolRegistry()
        ref = MCPToolRef(server="github", tool_name="create_pull_request")

        with self.assertRaises(ToolNotFoundError):
            resolve_mcp_tool_ref(ref, registry)


class TestRequestCapability(unittest.TestCase):
    def test_returns_matching_tool_regardless_of_protocol(self):
        registry = UniversalToolRegistry()
        registry.register_tool(make_contract("get_weather", protocol="rest", permissions=("weather",)))

        contract = request_capability(registry, "weather")

        self.assertEqual(contract.identity, "get_weather")

    def test_no_match_raises(self):
        registry = UniversalToolRegistry()
        with self.assertRaises(NoMatchingToolError):
            request_capability(registry, "nonexistent")


if __name__ == "__main__":
    unittest.main()
