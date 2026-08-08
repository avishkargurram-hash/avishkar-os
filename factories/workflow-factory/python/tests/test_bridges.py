import unittest

from avishkar_agent import (
    AgentBlueprint,
    ChiefDomainAgent,
    InMemoryMemoryPolicy,
    ToolRegistry,
)
from avishkar_agent.thinking import DEFAULT_THINKING_MODELS
from avishkar_knowledge import KnowledgeBase
from avishkar_router import ModelSpec, MockProvider, Router, RoutingPolicy

from avishkar_workflow import (
    make_agent_step,
    make_knowledge_search_step,
    make_memory_read_step,
    make_memory_write_step,
)


def _make_agent(response_text: str) -> ChiefDomainAgent:
    blueprint = AgentBlueprint(
        name="demo-agent", domain="Demo", version="0.1.0",
        mission="Answer demo questions.", default_model="mock-fast",
    )
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat",),
                           input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text=response_text,
    )
    router = Router([provider], RoutingPolicy(default_model="mock-fast"))
    return ChiefDomainAgent(blueprint, router, InMemoryMemoryPolicy(), ToolRegistry(), DEFAULT_THINKING_MODELS)


class TestMakeAgentStep(unittest.TestCase):
    def test_runs_agent_and_stores_result_under_output_key(self):
        agent = _make_agent("Here is your answer.")
        step = make_agent_step(agent)

        update = step({"input": "What's the status?"})

        self.assertIn("output", update)
        self.assertEqual(update["output"].status, "completed")
        self.assertEqual(update["output"].output, "Here is your answer.")

    def test_custom_input_and_output_keys(self):
        agent = _make_agent("ack")
        step = make_agent_step(agent, input_key="question", output_key="answer")

        update = step({"question": "hi"})

        self.assertIn("answer", update)
        self.assertNotIn("output", update)


class TestMakeKnowledgeSearchStep(unittest.TestCase):
    def test_runs_search_and_stores_results(self):
        kb = KnowledgeBase()
        kb.ingest("policy", "All deploys require a passing test suite and a code review.")
        step = make_knowledge_search_step(kb, top_k=1)

        update = step({"query": "what do we require before deploying"})

        self.assertEqual(len(update["knowledge_results"]), 1)
        self.assertEqual(update["knowledge_results"][0].chunk.document_id, "policy")


class TestMakeMemorySteps(unittest.TestCase):
    def test_write_then_read_round_trips(self):
        memory = InMemoryMemoryPolicy()
        write = make_memory_write_step(memory, "semantic", key_from_state="k", value_from_state="v")
        read = make_memory_read_step(memory, "semantic", key_from_state="k", output_key="recalled")

        write_update = write({"k": "deploy_day", "v": "Friday"})
        read_update = read({"k": "deploy_day"})

        self.assertEqual(write_update, {})
        self.assertEqual(read_update["recalled"], "Friday")

    def test_read_missing_key_returns_none(self):
        memory = InMemoryMemoryPolicy()
        read = make_memory_read_step(memory, "semantic", key_from_state="k", output_key="recalled")

        update = read({"k": "never-written"})

        self.assertIsNone(update["recalled"])


if __name__ == "__main__":
    unittest.main()
