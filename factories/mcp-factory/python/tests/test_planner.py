import unittest

from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router

from avishkar_integration import IntegrationPlanner, NoMatchingToolError, UniversalToolRegistry

from fixtures import FakeAdapter, make_contract


class _UnhealthyAdapter(FakeAdapter):
    """A second protocol whose health_check() always reports unhealthy,
    used only to give the planner two real, differently-healthy
    candidates without reaching into the registry's private state.
    """

    protocol_name = "fake-unhealthy"

    def health_check(self) -> str:
        return "unhealthy"


class TestIntegrationPlanner(unittest.TestCase):
    def test_no_matching_capability_raises(self):
        registry = UniversalToolRegistry()
        planner = IntegrationPlanner(registry)

        with self.assertRaises(NoMatchingToolError):
            planner.plan("nonexistent-capability")

    def test_picks_the_only_match(self):
        registry = UniversalToolRegistry()
        registry.register_tool(make_contract("search_code", permissions=("search",)))
        planner = IntegrationPlanner(registry)

        plan = planner.plan("search")

        self.assertEqual(plan.tool_contract.identity, "search_code")
        self.assertIn("search_code", plan.rationale)

    def test_prefers_healthy_over_unhealthy(self):
        registry = UniversalToolRegistry()
        registry.register_adapter(
            FakeAdapter(tools=(make_contract("search-healthy", permissions=("search",)),))
        )
        registry.register_adapter(
            _UnhealthyAdapter(tools=(make_contract("search-unhealthy", protocol="fake-unhealthy", permissions=("search",)),))
        )
        registry.health_check_all()

        planner = IntegrationPlanner(registry)
        plan = planner.plan("search")

        self.assertEqual(plan.tool_contract.identity, "search-healthy")

    def test_model_id_delegated_to_router_when_task_type_matches(self):
        registry = UniversalToolRegistry()
        registry.register_tool(make_contract("search_code", permissions=("search",)))

        provider = MockProvider(
            models=(
                ModelSpec(
                    model_id="mock-fast", provider="mock", capabilities=("chat", "search"),
                    input_cost_per_mtok=1.0, output_cost_per_mtok=1.0,
                    max_context_tokens=8192, max_output_tokens=2048,
                ),
            )
        )
        router = Router([provider], RoutingPolicy(default_model="mock-fast"))
        planner = IntegrationPlanner(registry, router=router)

        plan = planner.plan("search", task_type="search")

        self.assertEqual(plan.model_id, "mock-fast")

    def test_model_id_none_without_router(self):
        registry = UniversalToolRegistry()
        registry.register_tool(make_contract("search_code", permissions=("search",)))
        planner = IntegrationPlanner(registry)

        plan = planner.plan("search", task_type="search")

        self.assertIsNone(plan.model_id)


if __name__ == "__main__":
    unittest.main()
