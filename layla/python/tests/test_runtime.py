import unittest

from avishkar_agent import (
    AgentBlueprint,
    ApprovalGate,
    ChiefDomainAgent,
    InMemoryMemoryPolicy,
    Orchestrator,
    ToolRegistry,
)
from avishkar_agent.thinking import DEFAULT_THINKING_MODELS
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router

from avishkar_layla import LaylaMemoryPolicy
from avishkar_layla.runtime import ExecutiveRuntime
from avishkar_layla.scheduler import Scheduler
from avishkar_layla.types import COMPLETED, REQUIRES_HUMAN


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


def _runtime(agents, *, approval_gate=None):
    orchestrator = Orchestrator(list(agents))
    agent_domains = {a.name: a.domain for a in agents}
    memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
    return ExecutiveRuntime(
        orchestrator=orchestrator, agent_domains=agent_domains, memory=memory,
        approval_gate=approval_gate, clock=lambda: 0.0, sleep_fn=lambda s: None,
    )


class TestExecutiveRuntimeHappyPath(unittest.TestCase):
    def test_low_risk_single_agent_task_completes(self):
        runtime = _runtime([_agent("finance-agent", "Finance", "the ROI looks positive")])

        task = runtime.handle_event("What's the projected ROI, from a finance perspective?")

        self.assertEqual(task.state, COMPLETED)
        self.assertIn("the ROI looks positive", task.result)

    def test_audit_trail_is_recorded(self):
        runtime = _runtime([_agent("finance-agent", "Finance", "answer")])
        task = runtime.handle_event("What's the projected finance ROI?")

        history = runtime.audit.history(task.id)

        event_types = [record.event_type for record in history]
        self.assertIn("layla.task.received", event_types)
        self.assertIn("layla.plan.created", event_types)
        self.assertIn("layla.task.completed", event_types)

    def test_completed_task_is_persisted_in_session_store(self):
        runtime = _runtime([_agent("finance-agent", "Finance", "answer")])
        task = runtime.handle_event("What's the finance ROI?")

        loaded = runtime.sessions.load(task.id)

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.state, COMPLETED)


class TestExecutiveRuntimeUnknownCapability(unittest.TestCase):
    def test_unrecognized_request_requires_human(self):
        runtime = _runtime([_agent("finance-agent", "Finance", "x")])

        task = runtime.handle_event("something with absolutely no matching domain keywords zz")

        self.assertEqual(task.state, REQUIRES_HUMAN)
        self.assertIsNotNone(task.blocked_reason)


class TestExecutiveRuntimeApproval(unittest.TestCase):
    def test_high_risk_task_denied_by_gate_requires_human(self):
        gate = ApprovalGate(policy="always_ask", callback=lambda task: False)
        runtime = _runtime([_agent("finance-agent", "Finance", "x")], approval_gate=gate)

        task = runtime.handle_event("initiate a wire transfer for the finance team")

        self.assertEqual(task.state, REQUIRES_HUMAN)

    def test_high_risk_task_granted_by_gate_completes(self):
        gate = ApprovalGate(policy="always_allow")
        runtime = _runtime([_agent("finance-agent", "Finance", "transfer processed")], approval_gate=gate)

        task = runtime.handle_event("initiate a wire transfer for the finance team")

        self.assertEqual(task.state, COMPLETED)


class TestExecutiveRuntimeConflict(unittest.TestCase):
    def test_disagreeing_agents_require_human(self):
        legal = _agent("legal-agent", "Legal & Compliance", "This contract carries significant liability risk.")
        finance = _agent("finance-agent", "Finance & Economics", "Preheat the oven to 350 degrees before baking.")
        runtime = _runtime([legal, finance])

        task = runtime.handle_event("Review this from a legal and finance perspective.")

        self.assertEqual(task.state, REQUIRES_HUMAN)
        self.assertIn("conflict", task.blocked_reason.lower())


class TestExecutiveRuntimeScheduler(unittest.TestCase):
    def test_run_forever_ticks_scheduler_and_returns_iteration_count(self):
        scheduler = Scheduler(clock=lambda: 0.0)
        calls = []
        scheduler.schedule_once(0.0, lambda: calls.append(1))

        orchestrator = Orchestrator([_agent("finance-agent", "Finance", "x")])
        memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        runtime = ExecutiveRuntime(
            orchestrator=orchestrator, agent_domains={"finance-agent": "Finance"}, memory=memory,
            scheduler=scheduler, sleep_fn=lambda s: None,
        )

        iterations = runtime.run_forever(max_iterations=3, tick_interval_seconds=0.0)

        self.assertEqual(iterations, 3)
        self.assertEqual(calls, [1])  # one-shot job fires once, not on every tick


if __name__ == "__main__":
    unittest.main()
