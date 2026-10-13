import unittest

from avishkar_agent import AgentBlueprint, ApprovalGate, ChiefDomainAgent, InMemoryMemoryPolicy, Orchestrator, ToolRegistry
from avishkar_agent.thinking import DEFAULT_THINKING_MODELS
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router

from avishkar_layla import LaylaMemoryPolicy
from avishkar_layla.auth import AuthorizationManager
from avishkar_layla.errors import PermissionDeniedError, UnauthenticatedError
from avishkar_layla.identity import PERM_COMMAND, Principal, Role
from avishkar_layla.runtime import ExecutiveRuntime
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


def _runtime(agents, *, authorization=None, approval_gate=None):
    orchestrator = Orchestrator(list(agents))
    agent_domains = {a.name: a.domain for a in agents}
    memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
    return ExecutiveRuntime(
        orchestrator=orchestrator, agent_domains=agent_domains, memory=memory,
        authorization=authorization, approval_gate=approval_gate,
        clock=lambda: 0.0, sleep_fn=lambda s: None,
    )


class TestUnauthenticatedAccessIsRejected(unittest.TestCase):
    def test_no_session_id_raises_when_authorization_wired(self):
        auth = AuthorizationManager(clock=lambda: 0.0)
        runtime = _runtime([_agent("finance-agent", "Finance", "x")], authorization=auth)

        with self.assertRaises(UnauthenticatedError):
            runtime.handle_event("What's the finance outlook?")

    def test_expired_session_is_rejected(self):
        clock = [0.0]
        auth = AuthorizationManager(clock=lambda: clock[0])
        session = auth.issue_session(Principal(id="alice", kind="user"), ["operator"], ttl_seconds=10.0)
        runtime = _runtime([_agent("finance-agent", "Finance", "x")], authorization=auth)

        clock[0] += 11.0

        with self.assertRaises(UnauthenticatedError):
            runtime.handle_event("What's the finance outlook?", session_id=session.id)


class TestBackwardCompatibilityWithoutAuthorization(unittest.TestCase):
    def test_no_authorization_wired_behaves_exactly_like_phase_16(self):
        runtime = _runtime([_agent("finance-agent", "Finance", "answer")])
        task = runtime.handle_event("What's the finance outlook?")  # no session_id at all
        self.assertEqual(task.state, COMPLETED)


class TestRiskPermissionIntegration(unittest.TestCase):
    def test_viewer_cannot_trigger_a_high_risk_action_no_approval_even_requested(self):
        auth = AuthorizationManager(clock=lambda: 0.0)
        session = auth.issue_session(Principal(id="alice", kind="user"), ["viewer"])
        runtime = _runtime([_agent("finance-agent", "Finance", "x")], authorization=auth)

        task = runtime.handle_event("initiate a wire transfer for the finance team", session_id=session.id)

        self.assertEqual(task.state, REQUIRES_HUMAN)
        self.assertIn("lacks permission", task.blocked_reason)

    def test_admin_with_granting_gate_can_trigger_high_risk_action(self):
        auth = AuthorizationManager(clock=lambda: 0.0)
        session = auth.issue_session(Principal(id="alice", kind="user"), ["admin"])
        gate = ApprovalGate(policy="always_allow")
        runtime = _runtime([_agent("finance-agent", "Finance", "transfer processed")], authorization=auth, approval_gate=gate)

        task = runtime.handle_event("initiate a wire transfer for the finance team", session_id=session.id)

        self.assertEqual(task.state, COMPLETED)

    def test_operator_can_trigger_medium_risk_action(self):
        auth = AuthorizationManager(clock=lambda: 0.0)
        session = auth.issue_session(Principal(id="alice", kind="user"), ["operator"])
        gate = ApprovalGate(policy="always_allow")
        runtime = _runtime([_agent("finance-agent", "Finance", "meeting scheduled")], authorization=auth, approval_gate=gate)

        task = runtime.handle_event("schedule a meeting with the finance team", session_id=session.id)

        self.assertEqual(task.state, COMPLETED)


class TestCapabilityRestrictionIntegration(unittest.TestCase):
    def test_role_scoped_to_one_capability_blocks_a_plan_naming_another(self):
        auth = AuthorizationManager(clock=lambda: 0.0)
        auth.register_role(Role("finance-only", (PERM_COMMAND, "agent.invoke"), allowed_capabilities=("finance-economics",)))
        session = auth.issue_session(Principal(id="alice", kind="user"), ["finance-only"])

        legal = _agent("legal-compliance", "Legal & Compliance", "x")
        finance = _agent("finance-economics", "Finance & Economics", "x")
        runtime = _runtime([legal, finance], authorization=auth)

        task = runtime.handle_event("Please review this from a legal compliance perspective.", session_id=session.id)

        self.assertEqual(task.state, REQUIRES_HUMAN)
        self.assertIn("not permitted", task.blocked_reason)


class TestAgentPrincipalStructuralCeiling(unittest.TestCase):
    def test_an_agent_kind_principal_can_never_be_issued_high_risk_authority(self):
        # Proven at issue_session() already (test_auth.py); here we
        # confirm the *consequence* end to end: an agent-kind session
        # (the "agent" role) hits the same risk-permission wall a human
        # without admin would.
        auth = AuthorizationManager(clock=lambda: 0.0)
        session = auth.issue_session(Principal(id="research-intelligence", kind="agent"), ["agent"])
        runtime = _runtime([_agent("finance-agent", "Finance", "x")], authorization=auth)

        task = runtime.handle_event("initiate a wire transfer for the finance team", session_id=session.id)

        self.assertEqual(task.state, REQUIRES_HUMAN)


class TestAuditTrailIncludesPrincipal(unittest.TestCase):
    def test_audit_records_carry_the_requesting_principal(self):
        auth = AuthorizationManager(clock=lambda: 0.0)
        session = auth.issue_session(Principal(id="alice", kind="user"), ["operator"])
        runtime = _runtime([_agent("finance-agent", "Finance", "answer")], authorization=auth)

        task = runtime.handle_event("What's the finance outlook?", session_id=session.id)

        history = runtime.audit.history(task.id)
        self.assertTrue(all(r.principal_id == "alice" for r in history))


if __name__ == "__main__":
    unittest.main()
