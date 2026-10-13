import unittest

from avishkar_agent import MCPServerNotAvailableError, MCPToolRef, Tool, ToolNotFoundError, ToolRegistry


class TestToolRegistry(unittest.TestCase):
    def test_register_and_call_a_tool(self):
        registry = ToolRegistry()
        registry.register(Tool(name="add_one", call=lambda x: x + 1))

        self.assertEqual(registry.call("add_one", 4), 5)

    def test_call_unregistered_tool_raises(self):
        registry = ToolRegistry()
        with self.assertRaises(ToolNotFoundError):
            registry.call("nonexistent", None)

    def test_mcp_tool_ref_raises_not_available(self):
        registry = ToolRegistry()
        registry.register(MCPToolRef(server="github", tool_name="create_pr"))

        with self.assertRaises(MCPServerNotAvailableError):
            registry.call("mcp:github/create_pr", {"title": "..."})

    def test_list_names(self):
        registry = ToolRegistry()
        registry.register(Tool(name="a", call=lambda x: x))
        registry.register(MCPToolRef(server="s", tool_name="t"))

        names = set(registry.list_names())
        self.assertEqual(names, {"a", "mcp:s/t"})

    def test_get_returns_none_for_unknown(self):
        registry = ToolRegistry()
        self.assertIsNone(registry.get("nonexistent"))


if __name__ == "__main__":
    unittest.main()
