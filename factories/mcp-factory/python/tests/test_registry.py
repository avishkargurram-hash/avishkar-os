import unittest

from avishkar_integration import (
    DuplicateAdapterError,
    ProtocolNotRegisteredError,
    ToolNotFoundError,
    UniversalToolRegistry,
)

from fixtures import FakeAdapter, make_contract


class TestUniversalToolRegistryRegistration(unittest.TestCase):
    def test_register_adapter_discovers_and_registers_tools(self):
        adapter = FakeAdapter(tools=(make_contract("a"), make_contract("b")))
        registry = UniversalToolRegistry()

        registry.register_adapter(adapter)

        self.assertEqual(len(registry.list_tools()), 2)
        self.assertEqual(registry.get("fake", "a").identity, "a")

    def test_duplicate_adapter_raises(self):
        registry = UniversalToolRegistry()
        registry.register_adapter(FakeAdapter())
        with self.assertRaises(DuplicateAdapterError):
            registry.register_adapter(FakeAdapter())

    def test_register_tool_directly(self):
        registry = UniversalToolRegistry()
        registry.register_tool(make_contract("standalone"))
        self.assertEqual(registry.get("fake", "standalone").identity, "standalone")


class TestUniversalToolRegistryLookup(unittest.TestCase):
    def test_get_unknown_tool_raises(self):
        registry = UniversalToolRegistry()
        with self.assertRaises(ToolNotFoundError):
            registry.get("fake", "nonexistent")

    def test_get_adapter_unknown_protocol_raises(self):
        registry = UniversalToolRegistry()
        with self.assertRaises(ProtocolNotRegisteredError):
            registry.get_adapter("nonexistent")

    def test_list_tools_filters_by_protocol(self):
        registry = UniversalToolRegistry()
        registry.register_tool(make_contract("a", protocol="rest"))
        registry.register_tool(make_contract("b", protocol="mcp"))

        rest_tools = registry.list_tools(protocol="rest")

        self.assertEqual([t.identity for t in rest_tools], ["a"])

    def test_find_by_capability_matches_permissions_identity_description(self):
        registry = UniversalToolRegistry()
        registry.register_tool(make_contract("search_code", permissions=("read_code",)))
        registry.register_tool(make_contract("deploy", description="deploys to production"))

        by_permission = registry.find_by_capability("read_code")
        by_identity = registry.find_by_capability("search")
        by_description = registry.find_by_capability("production")

        self.assertEqual([t.identity for t in by_permission], ["search_code"])
        self.assertEqual([t.identity for t in by_identity], ["search_code"])
        self.assertEqual([t.identity for t in by_description], ["deploy"])


class TestUniversalToolRegistryHealth(unittest.TestCase):
    def test_health_check_all_updates_health(self):
        adapter = FakeAdapter(tools=(make_contract("a"),))
        registry = UniversalToolRegistry()
        registry.register_adapter(adapter)

        health = registry.health_check_all()

        self.assertEqual(health["fake:a"], "healthy")
        self.assertEqual(registry.get_health("fake", "a"), "healthy")

    def test_get_health_unknown_tool_raises(self):
        registry = UniversalToolRegistry()
        with self.assertRaises(ToolNotFoundError):
            registry.get_health("fake", "nonexistent")


if __name__ == "__main__":
    unittest.main()
