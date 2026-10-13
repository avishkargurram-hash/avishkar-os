import unittest

from avishkar_agent import MCPServerNotAvailableError, Task
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router

from startup_business_product_agent import (
    _classify_market_size,
    _no_binding_business_commitments,
    _score_pitch_clarity,
    build_startup_business_product_agent,
    load_blueprint,
)


def _router(response_text: str = "Here is a structured PRD outline.") -> Router:
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat", "tools"),
                           input_cost_per_mtok=1.0, output_cost_per_mtok=1.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text=response_text,
    )
    return Router([provider], RoutingPolicy(default_model="mock-fast"))


class TestBlueprint(unittest.TestCase):
    def test_loads_committed_blueprint(self):
        blueprint = load_blueprint()
        self.assertEqual(blueprint.name, "startup-business-product")
        self.assertIn("prd-writer", blueprint.sub_agent_roles)


class TestScorePitchClarityTool(unittest.TestCase):
    def test_detects_all_sections(self):
        text = "The problem is X. Our solution is Y. The market is large. Our ask is $2M."
        scores = _score_pitch_clarity(text)
        self.assertTrue(all(scores.values()))

    def test_detects_missing_section(self):
        text = "The problem is X. Our solution is Y."
        scores = _score_pitch_clarity(text)
        self.assertFalse(scores["market"])
        self.assertFalse(scores["ask"])


class TestClassifyMarketSizeTool(unittest.TestCase):
    def test_large_market_keywords(self):
        self.assertEqual(_classify_market_size("This is a billion-dollar global market."), "large")

    def test_niche_market_keywords(self):
        self.assertEqual(_classify_market_size("This targets a niche group of enthusiasts."), "niche")

    def test_unclear_default(self):
        self.assertEqual(_classify_market_size("We sell software to companies."), "unclear")


class TestGuardrail(unittest.TestCase):
    def test_blocks_binding_commitment_request(self):
        reason = _no_binding_business_commitments(Task(input="Please sign this term sheet on my behalf"))
        self.assertIsNotNone(reason)

    def test_allows_ordinary_question(self):
        self.assertIsNone(_no_binding_business_commitments(Task(input="How should I structure my PRD?")))


class TestAgentIntegration(unittest.TestCase):
    def test_normal_task_completes(self):
        agent = build_startup_business_product_agent(_router(), model_override="mock-fast")
        result = agent.handle(Task(input="Help me structure a PRD for my new product."))
        self.assertEqual(result.status, "completed")

    def test_binding_commitment_request_is_blocked(self):
        agent = build_startup_business_product_agent(_router(), model_override="mock-fast")
        result = agent.handle(Task(input="Please sign this term sheet on my behalf"))
        self.assertEqual(result.status, "blocked")

    def test_declared_mcp_tool_raises_typed_error(self):
        agent = build_startup_business_product_agent(_router(), model_override="mock-fast")
        with self.assertRaises(MCPServerNotAvailableError):
            agent.tools.call("mcp:crunchbase/get_company_data", "competitor X")

    def test_knowledge_search_tool_is_callable(self):
        agent = build_startup_business_product_agent(_router(), model_override="mock-fast")
        results = agent.tools.call("search_startup_playbooks", "what should a PRD include")
        self.assertTrue(results)

    def test_sub_agent_routing_to_prd_writer(self):
        agent = build_startup_business_product_agent(_router(), model_override="mock-fast")
        role = agent.route_to_sub_agent_role(Task(input="Can the prd-writer draft this?"))
        self.assertEqual(role, "prd-writer")


if __name__ == "__main__":
    unittest.main()
