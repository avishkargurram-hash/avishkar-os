"""ExecutiveRuntime + PersonalModel wiring (Mission Layla, Part 1)."""

import unittest

from avishkar_agent import AgentBlueprint, ChiefDomainAgent, InMemoryMemoryPolicy, Orchestrator, ToolRegistry
from avishkar_agent.thinking import DEFAULT_THINKING_MODELS
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router

from avishkar_layla import LaylaMemoryPolicy, PersonalModel
from avishkar_layla.personal_model import CATEGORY_COMMUNICATION_STYLE
from avishkar_layla.runtime import ExecutiveRuntime
from avishkar_layla.types import COMPLETED


def _agent(name: str, domain: str, response_text: str) -> ChiefDomainAgent:
    blueprint = AgentBlueprint(name=name, domain=domain, version="0.1.0", mission="test", default_model="mock-fast")
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat",),
                           input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text=response_text,
    )
    router = Router([provider], RoutingPolicy(default_model="mock-fast"))
    return ChiefDomainAgent(blueprint, router, InMemoryMemoryPolicy(), ToolRegistry(), DEFAULT_THINKING_MODELS)


class TestExecutiveRuntimePersonalModelWiring(unittest.TestCase):
    def test_personal_model_summary_appears_in_task_context(self):
        memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        personal_model = PersonalModel(memory)
        personal_model.set(CATEGORY_COMMUNICATION_STYLE, "tone", "direct, no fluff")

        orchestrator = Orchestrator([_agent("finance-agent", "Finance", "answer")])
        runtime = ExecutiveRuntime(
            orchestrator=orchestrator, agent_domains={"finance-agent": "Finance"}, memory=memory,
            personal_model=personal_model, clock=lambda: 0.0, sleep_fn=lambda s: None,
        )

        task = runtime.handle_event("What's the finance ROI?")

        self.assertEqual(task.state, COMPLETED)
        self.assertIn("communication_style", task.context["personal_model_summary"])
        self.assertIn("direct, no fluff", task.context["personal_model_summary"])
        self.assertIs(runtime.personal_model, personal_model)

    def test_personal_model_is_optional_and_defaults_to_none(self):
        memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        orchestrator = Orchestrator([_agent("finance-agent", "Finance", "answer")])
        runtime = ExecutiveRuntime(
            orchestrator=orchestrator, agent_domains={"finance-agent": "Finance"}, memory=memory,
            clock=lambda: 0.0, sleep_fn=lambda s: None,
        )

        task = runtime.handle_event("What's the finance ROI?")

        self.assertEqual(task.state, COMPLETED)  # unchanged prior behavior
        self.assertNotIn("personal_model_summary", task.context)
        self.assertIsNone(runtime.personal_model)


if __name__ == "__main__":
    unittest.main()
