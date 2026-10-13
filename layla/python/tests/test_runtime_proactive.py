"""ExecutiveRuntime + ProactiveEngine wiring (Mission Layla, Part 2/11)."""

import unittest

from avishkar_agent import AgentBlueprint, ChiefDomainAgent, InMemoryMemoryPolicy, Orchestrator, ToolRegistry
from avishkar_agent.thinking import DEFAULT_THINKING_MODELS
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router

from avishkar_layla import LaylaMemoryPolicy
from avishkar_layla.proactive import ACTION_ACT, ProactiveTrigger
from avishkar_layla.runtime import ExecutiveRuntime


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


def _always_act_on_finance(self):
    return (ProactiveTrigger(
        id="watchlist-check", action_level=ACTION_ACT,
        description="Check the finance watchlist for anything noteworthy.",
        evidence={"reason": "test-forced-trigger"}, source="test.custom",
    ),)


class TestExecutiveRuntimeProactiveDisabledByDefault(unittest.TestCase):
    def test_proactive_is_none_and_run_forever_does_not_touch_it(self):
        memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        orchestrator = Orchestrator([_agent("finance-agent", "Finance", "answer")])
        runtime = ExecutiveRuntime(
            orchestrator=orchestrator, agent_domains={"finance-agent": "Finance"}, memory=memory,
            clock=lambda: 0.0, sleep_fn=lambda s: None,
        )

        self.assertIsNone(runtime.proactive)
        iterations = runtime.run_forever(max_iterations=3, tick_interval_seconds=0.0)
        self.assertEqual(iterations, 3)  # runs fine with nothing wired


class TestExecutiveRuntimeProactiveActFlow(unittest.TestCase):
    def test_a_custom_act_trigger_drives_a_real_handle_event_call(self):
        memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        orchestrator = Orchestrator([_agent("finance-agent", "Finance", "watchlist looks fine")])
        runtime = ExecutiveRuntime(
            orchestrator=orchestrator, agent_domains={"finance-agent": "Finance"}, memory=memory,
            enable_proactive=True, proactive_evaluators=(_always_act_on_finance,),
            clock=lambda: 0.0, sleep_fn=lambda s: None,
        )

        self.assertIsNotNone(runtime.proactive)
        runtime.run_forever(max_iterations=1, tick_interval_seconds=0.0)

        # A real task was created and driven all the way to COMPLETED
        # through the exact same pipeline handle_event() itself uses --
        # not a bypass.
        incomplete = runtime.sessions.list_incomplete()
        self.assertEqual(incomplete, ())  # nothing left dangling
        act_events = [
            r for r in runtime.audit.history(task_id=None)
            if r.event_type == "layla.proactive.act_triggered"
        ]
        self.assertEqual(len(act_events), 1)
        self.assertTrue(act_events[0].payload["callback_wired"])

    def test_evaluate_can_also_be_called_directly_without_run_forever(self):
        memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        orchestrator = Orchestrator([_agent("finance-agent", "Finance", "watchlist looks fine")])
        runtime = ExecutiveRuntime(
            orchestrator=orchestrator, agent_domains={"finance-agent": "Finance"}, memory=memory,
            enable_proactive=True, proactive_evaluators=(_always_act_on_finance,),
            clock=lambda: 0.0, sleep_fn=lambda s: None,
        )

        triggers = runtime.proactive.evaluate()

        self.assertEqual(len(triggers), 1)
        self.assertEqual(triggers[0].action_level, ACTION_ACT)


if __name__ == "__main__":
    unittest.main()
