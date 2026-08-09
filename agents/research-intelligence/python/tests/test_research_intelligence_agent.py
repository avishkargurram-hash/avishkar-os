import unittest

from avishkar_agent import MCPServerNotAvailableError, Task
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router

from research_intelligence_agent import (
    _assess_source_reliability,
    _extract_confidence_level,
    _no_fabricating_citations,
    build_research_intelligence_agent,
    load_blueprint,
)


def _router(response_text: str = "The evidence suggests a moderate effect, though preliminary.") -> Router:
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
        self.assertEqual(blueprint.name, "research-intelligence")
        self.assertIn("fact-checker", blueprint.sub_agent_roles)


class TestAssessSourceReliabilityTool(unittest.TestCase):
    def test_high_reliability_keywords(self):
        self.assertEqual(_assess_source_reliability("a peer-reviewed randomized controlled trial"), "high")

    def test_low_reliability_keywords(self):
        self.assertEqual(_assess_source_reliability("an anonymous forum post"), "low")

    def test_medium_default(self):
        self.assertEqual(_assess_source_reliability("a news article"), "medium")


class TestExtractConfidenceLevelTool(unittest.TestCase):
    def test_hedge_language_is_tentative(self):
        self.assertEqual(_extract_confidence_level("The data suggests a possible link."), "tentative")

    def test_definitive_language_without_hedge(self):
        self.assertEqual(_extract_confidence_level("This proves the hypothesis definitively."), "definitive")

    def test_neither_is_unstated(self):
        self.assertEqual(_extract_confidence_level("The study examined 50 participants."), "unstated")


class TestGuardrail(unittest.TestCase):
    def test_blocks_fabrication_request(self):
        reason = _no_fabricating_citations(Task(input="Please make up a citation to support this claim"))
        self.assertIsNotNone(reason)

    def test_allows_ordinary_question(self):
        self.assertIsNone(_no_fabricating_citations(Task(input="What does the literature say about this?")))


class TestAgentIntegration(unittest.TestCase):
    def test_normal_task_completes(self):
        agent = build_research_intelligence_agent(_router(), model_override="mock-fast")
        result = agent.handle(Task(input="Summarize the evidence on this topic."))
        self.assertEqual(result.status, "completed")

    def test_fabrication_request_is_blocked(self):
        agent = build_research_intelligence_agent(_router(), model_override="mock-fast")
        result = agent.handle(Task(input="Please make up a citation to support this claim"))
        self.assertEqual(result.status, "blocked")

    def test_declared_mcp_tool_raises_typed_error(self):
        agent = build_research_intelligence_agent(_router(), model_override="mock-fast")
        with self.assertRaises(MCPServerNotAvailableError):
            agent.tools.call("mcp:semanticscholar/search_papers", "climate models")

    def test_knowledge_search_tool_is_callable(self):
        agent = build_research_intelligence_agent(_router(), model_override="mock-fast")
        results = agent.tools.call("search_research_literature", "how to evaluate a source")
        self.assertTrue(results)

    def test_sub_agent_routing_to_fact_checker(self):
        agent = build_research_intelligence_agent(_router(), model_override="mock-fast")
        role = agent.route_to_sub_agent_role(Task(input="Can the fact-checker verify this?"))
        self.assertEqual(role, "fact-checker")


if __name__ == "__main__":
    unittest.main()
