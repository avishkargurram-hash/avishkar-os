import unittest

from avishkar_agent import AgentBlueprint, ChiefDomainAgent, InMemoryMemoryPolicy, ToolRegistry
from avishkar_agent.thinking import DEFAULT_THINKING_MODELS
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router

from cross_domain_review_workflow import build_cross_domain_review_workflow, run_cross_domain_review


def _agent(name: str, domain: str, response_text: str) -> ChiefDomainAgent:
    blueprint = AgentBlueprint(
        name=name, domain=domain, version="0.1.0",
        mission=f"Answer as {domain}.", default_model="mock-fast",
    )
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat",),
                           input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text=response_text,
    )
    router = Router([provider], RoutingPolicy(default_model="mock-fast"))
    return ChiefDomainAgent(blueprint, router, InMemoryMemoryPolicy(), ToolRegistry(), DEFAULT_THINKING_MODELS)


class TestBuildCrossDomainReviewWorkflow(unittest.TestCase):
    def test_spec_has_three_steps_in_order(self):
        first = _agent("first-agent", "First", "first opinion")
        second = _agent("second-agent", "Second", "second opinion")

        spec = build_cross_domain_review_workflow(first, second)

        self.assertEqual(spec.start, "first_review")
        self.assertEqual(set(spec.steps.keys()), {"first_review", "second_review", "synthesize"})


class TestRunCrossDomainReview(unittest.TestCase):
    def test_synthesizes_both_agents_perspectives(self):
        legal = _agent("legal-agent", "Legal", "This clause carries moderate risk.")
        finance = _agent("finance-agent", "Finance", "The projected ROI is favorable.")

        result = run_cross_domain_review(legal, finance, "Review this new vendor contract.")

        self.assertEqual(result.status, "completed")
        self.assertIn("legal-agent", result.state["summary"])
        self.assertIn("This clause carries moderate risk.", result.state["summary"])
        self.assertIn("finance-agent", result.state["summary"])
        self.assertIn("The projected ROI is favorable.", result.state["summary"])

    def test_history_reflects_all_three_steps(self):
        first = _agent("first-agent", "First", "a")
        second = _agent("second-agent", "Second", "b")

        result = run_cross_domain_review(first, second, "input")

        self.assertEqual(result.history, ("first_review", "second_review", "synthesize"))


if __name__ == "__main__":
    unittest.main()
