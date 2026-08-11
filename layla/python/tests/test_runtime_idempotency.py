"""ExecutiveRuntime + ExecutionTracker wiring (Priority 17.2). Proves
`execution_tracker=` reaches DelegationEngine through the full
handle_event() pipeline and leaves a real, inspectable ExecutionRecord
behind -- not just that DelegationEngine's own unit tests pass in
isolation.
"""

import unittest

from avishkar_agent import (
    AgentBlueprint,
    ChiefDomainAgent,
    InMemoryMemoryPolicy,
    Orchestrator,
    ToolRegistry,
)
from avishkar_agent.thinking import DEFAULT_THINKING_MODELS
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router

from avishkar_layla import EXEC_COMPLETED, ExecutionTracker, LaylaMemoryPolicy
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


class TestExecutiveRuntimeExecutionTrackerWiring(unittest.TestCase):
    def test_completed_delegation_leaves_a_real_execution_record(self):
        agent = _agent("finance-agent", "Finance", "the ROI looks positive")
        orchestrator = Orchestrator([agent])
        memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        tracker = ExecutionTracker(memory, clock=lambda: 0.0)
        runtime = ExecutiveRuntime(
            orchestrator=orchestrator, agent_domains={"finance-agent": "Finance"}, memory=memory,
            execution_tracker=tracker, clock=lambda: 0.0, sleep_fn=lambda s: None,
        )

        task = runtime.handle_event("What's the projected ROI, from a finance perspective?")
        self.assertEqual(task.state, COMPLETED)

        self.assertIs(runtime.executions, tracker)
        delegation_events = [
            r for r in runtime.audit.history(task.id) if r.event_type == "layla.delegation.completed"
        ]
        self.assertEqual(len(delegation_events), 1)
        step_id = delegation_events[0].payload["step_id"]

        record = tracker.get(f"{task.id}:{step_id}")
        self.assertIsNotNone(record)
        self.assertEqual(record.status, EXEC_COMPLETED)

    def test_execution_tracker_is_optional_and_defaults_to_none(self):
        agent = _agent("finance-agent", "Finance", "answer")
        orchestrator = Orchestrator([agent])
        memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        runtime = ExecutiveRuntime(
            orchestrator=orchestrator, agent_domains={"finance-agent": "Finance"}, memory=memory,
            clock=lambda: 0.0, sleep_fn=lambda s: None,
        )

        task = runtime.handle_event("What's the finance ROI?")

        self.assertEqual(task.state, COMPLETED)  # unchanged Phase 16/17.1 behavior
        self.assertIsNone(runtime.executions)


if __name__ == "__main__":
    unittest.main()
