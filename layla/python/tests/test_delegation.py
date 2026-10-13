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
from avishkar_core import EventBus
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router

from avishkar_layla import RISK_HIGH, RISK_LOW, PlanStep
from avishkar_layla.approval import ApprovalManager
from avishkar_layla.delegation import DelegationEngine


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


class TestDelegationEngine(unittest.TestCase):
    def test_successful_delegation(self):
        orchestrator = Orchestrator([_agent("finance-agent", "Finance", "the answer")])
        engine = DelegationEngine(orchestrator, clock=lambda: 0.0, sleep_fn=lambda s: None)
        step = PlanStep(id="s1", required_capability="finance-agent", input="What's the ROI?")

        record = engine.delegate(step, task_id="t1")

        self.assertEqual(record.status, "completed")
        self.assertEqual(record.output, "the answer")
        self.assertEqual(record.attempts, 1)

    def test_unknown_capability_fails_without_retry(self):
        orchestrator = Orchestrator([_agent("finance-agent", "Finance", "x")])
        engine = DelegationEngine(orchestrator, clock=lambda: 0.0, sleep_fn=lambda s: None)
        step = PlanStep(id="s1", required_capability="astrophysics", input="?", max_attempts=3)

        record = engine.delegate(step, task_id="t1")

        self.assertEqual(record.status, "failed")
        self.assertEqual(record.attempts, 1)  # no point retrying a capability that doesn't exist

    def test_timeout_is_detected(self):
        orchestrator = Orchestrator([_agent("finance-agent", "Finance", "x")])
        # Clock jumps by more than the step's timeout on every call.
        ticks = iter([0.0, 100.0, 100.0, 200.0])
        engine = DelegationEngine(orchestrator, clock=lambda: next(ticks), sleep_fn=lambda s: None)
        step = PlanStep(id="s1", required_capability="finance-agent", input="?", timeout_seconds=5.0)

        record = engine.delegate(step, task_id="t1")

        self.assertEqual(record.status, "timeout")

    def test_high_risk_step_requires_approval_and_is_denied(self):
        gate = ApprovalGate(policy="always_ask", callback=lambda task: False)
        approval_manager = ApprovalManager(approval_gate=gate)
        orchestrator = Orchestrator([_agent("finance-agent", "Finance", "x")])
        engine = DelegationEngine(orchestrator, approval_manager=approval_manager, clock=lambda: 0.0, sleep_fn=lambda s: None)
        step = PlanStep(id="s1", required_capability="finance-agent", input="wire transfer $10k", risk_level=RISK_HIGH)

        record = engine.delegate(step, task_id="t1")

        self.assertEqual(record.status, "denied")

    def test_low_risk_step_does_not_need_approval(self):
        approval_manager = ApprovalManager()  # no gate wired -- would stay pending if consulted
        orchestrator = Orchestrator([_agent("finance-agent", "Finance", "x")])
        engine = DelegationEngine(orchestrator, approval_manager=approval_manager, clock=lambda: 0.0, sleep_fn=lambda s: None)
        step = PlanStep(id="s1", required_capability="finance-agent", input="summarize", risk_level=RISK_LOW)

        record = engine.delegate(step, task_id="t1")

        self.assertEqual(record.status, "completed")

    def test_delegation_is_published_to_event_bus(self):
        bus = EventBus()
        received = []
        bus.subscribe("*", lambda event: received.append(event))
        orchestrator = Orchestrator([_agent("finance-agent", "Finance", "x")])
        engine = DelegationEngine(orchestrator, event_bus=bus, clock=lambda: 0.0, sleep_fn=lambda s: None)
        step = PlanStep(id="s1", required_capability="finance-agent", input="?")

        engine.delegate(step, task_id="t1")

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].event_type, "layla.delegation.completed")
        self.assertEqual(received[0].payload["task_id"], "t1")


if __name__ == "__main__":
    unittest.main()
