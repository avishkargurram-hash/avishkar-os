import unittest

from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router

from avishkar_agent import (
    AgentBlueprint,
    ApprovalGate,
    ChiefDomainAgent,
    Guardrail,
    InMemoryMemoryPolicy,
    QualityGate,
    Task,
    ToolRegistry,
)
from avishkar_agent.thinking import DEFAULT_THINKING_MODELS


def _router() -> Router:
    provider = MockProvider(
        models=(
            ModelSpec(
                model_id="mock-fast",
                provider="mock",
                capabilities=("chat",),
                input_cost_per_mtok=1.0,
                output_cost_per_mtok=1.0,
                max_context_tokens=8192,
                max_output_tokens=2048,
            ),
        ),
        response_text="Recommend adding a read-through cache with a 60s TTL.",
    )
    return Router([provider], RoutingPolicy(default_model="mock-fast"))


def _blueprint(**overrides) -> AgentBlueprint:
    data = dict(
        name="test-agent",
        domain="Test Domain",
        version="0.1.0",
        mission="Answer test questions correctly.",
        default_model="mock-fast",
        reasoning_strategies=("first_principles", "systems_thinking"),
    )
    data.update(overrides)
    return AgentBlueprint(**data)


def _agent(blueprint=None, **kwargs) -> ChiefDomainAgent:
    return ChiefDomainAgent(
        blueprint=blueprint or _blueprint(),
        router=_router(),
        memory=InMemoryMemoryPolicy(),
        tools=ToolRegistry(),
        thinking_models=DEFAULT_THINKING_MODELS,
        **kwargs,
    )


class TestChiefDomainAgentHandle(unittest.TestCase):
    def test_completes_and_returns_output(self):
        agent = _agent()
        result = agent.handle(Task(input="design a caching layer"))

        self.assertEqual(result.status, "completed")
        self.assertIn("cache", result.output.lower())
        self.assertEqual(result.agent_name, "test-agent")
        self.assertGreaterEqual(result.iterations, 1)

    def test_thinking_trace_records_plan_and_reflect_steps(self):
        agent = _agent()
        result = agent.handle(Task(input="design a caching layer"))

        strategies = [step.strategy for step in result.thinking_trace]
        self.assertIn("first_principles", strategies)
        self.assertIn("reflection", strategies)

    def test_reasoning_strategy_rotates_across_iterations(self):
        # Force 2 iterations via a quality gate that fails once.
        calls = {"count": 0}

        def flaky_gate(result):
            calls["count"] += 1
            return calls["count"] > 1  # fail first check, pass second

        agent = _agent(quality_gates=(QualityGate(name="flaky", check=flaky_gate),))
        result = agent.handle(Task(input="design a caching layer"))

        plan_strategies = [s.strategy for s in result.thinking_trace if s.strategy != "reflection"]
        self.assertEqual(plan_strategies[:2], ["first_principles", "systems_thinking"])
        self.assertEqual(result.iterations, 2)


class TestChiefDomainAgentGuardrails(unittest.TestCase):
    def test_guardrail_blocks_before_any_model_call(self):
        guardrail = Guardrail(name="no-secrets", check=lambda task: "contains a secret" if "password" in task.input else None)
        agent = _agent(guardrails=(guardrail,))

        result = agent.handle(Task(input="print the admin password"))

        self.assertEqual(result.status, "blocked")
        self.assertIn("no-secrets", result.blocked_reason)
        self.assertEqual(result.iterations, 0)
        self.assertEqual(result.cost_usd, 0.0)

    def test_passing_guardrail_does_not_block(self):
        guardrail = Guardrail(name="no-secrets", check=lambda task: None)
        agent = _agent(guardrails=(guardrail,))

        result = agent.handle(Task(input="design a caching layer"))

        self.assertEqual(result.status, "completed")


class TestChiefDomainAgentApprovalGate(unittest.TestCase):
    def test_denied_approval_blocks_task(self):
        gate = ApprovalGate(policy="always_ask", callback=lambda task: False)
        agent = _agent(approval_gate=gate)

        result = agent.handle(Task(input="deploy to production"))

        self.assertEqual(result.status, "blocked")
        self.assertIn("approval_gate", result.blocked_reason)

    def test_allowed_approval_proceeds(self):
        gate = ApprovalGate(policy="always_ask", callback=lambda task: True)
        agent = _agent(approval_gate=gate)

        result = agent.handle(Task(input="deploy to production"))

        self.assertEqual(result.status, "completed")


class TestChiefDomainAgentQualityGates(unittest.TestCase):
    def test_exhausting_iterations_on_failing_gate_yields_failed_status(self):
        always_fail = QualityGate(name="never-passes", check=lambda result: False)
        agent = _agent(
            blueprint=_blueprint(max_iterations=2),
            quality_gates=(always_fail,),
        )

        result = agent.handle(Task(input="design a caching layer"))

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.iterations, 2)


class TestChiefDomainAgentSubAgentRouting(unittest.TestCase):
    def test_routes_to_matching_role_by_keyword(self):
        blueprint = _blueprint(sub_agent_roles=("architect", "debugger"))
        agent = _agent(blueprint=blueprint)

        role = agent.route_to_sub_agent_role(Task(input="act as the debugger and find this bug"))

        self.assertEqual(role, "debugger")

    def test_routes_to_hyphenated_role_regardless_of_hyphen_or_space_in_task(self):
        # Regression test: the default router must normalize hyphens on
        # BOTH the role name and the task text, not just one side --
        # examples/quickstart.py caught this failing silently (falling
        # back to the first role) before the fix.
        blueprint = _blueprint(sub_agent_roles=("architect", "security-auditor"))
        agent = _agent(blueprint=blueprint)

        hyphenated = agent.route_to_sub_agent_role(Task(input="act as the security-auditor here"))
        spaced = agent.route_to_sub_agent_role(Task(input="act as the security auditor here"))

        self.assertEqual(hyphenated, "security-auditor")
        self.assertEqual(spaced, "security-auditor")

    def test_falls_back_to_first_role_when_no_keyword_matches(self):
        blueprint = _blueprint(sub_agent_roles=("architect", "debugger"))
        agent = _agent(blueprint=blueprint)

        role = agent.route_to_sub_agent_role(Task(input="something unrelated"))

        self.assertEqual(role, "architect")

    def test_returns_none_when_no_roles_declared(self):
        agent = _agent(blueprint=_blueprint(sub_agent_roles=()))

        role = agent.route_to_sub_agent_role(Task(input="anything"))

        self.assertIsNone(role)


if __name__ == "__main__":
    unittest.main()
