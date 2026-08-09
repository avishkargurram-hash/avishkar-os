import unittest

from avishkar_agent import MCPServerNotAvailableError, Task
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router

from government_public_policy_agent import (
    _check_policy_structure,
    _classify_regulatory_scope,
    _no_issuing_binding_rulings,
    build_government_public_policy_agent,
    load_blueprint,
)


def _router(response_text: str = "Submit input through the agency's official public comment channel.") -> Router:
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
        self.assertEqual(blueprint.name, "government-public-policy")
        self.assertIn("policy-analyst", blueprint.sub_agent_roles)


class TestCheckPolicyStructureTool(unittest.TestCase):
    def test_detects_all_sections(self):
        text = "The objective is X. Stakeholders include Y. Budget impact is $1M. Implementation timeline is 6 months."
        self.assertTrue(all(_check_policy_structure(text).values()))

    def test_detects_missing_section(self):
        text = "The objective is X."
        result = _check_policy_structure(text)
        self.assertFalse(result["stakeholders"])
        self.assertFalse(result["budget_impact"])


class TestClassifyRegulatoryScopeTool(unittest.TestCase):
    def test_federal_keywords(self):
        self.assertEqual(_classify_regulatory_scope("This is a federal regulation from Congress."), "federal")

    def test_state_keywords(self):
        self.assertEqual(_classify_regulatory_scope("This falls under state law."), "state")

    def test_local_keywords(self):
        self.assertEqual(_classify_regulatory_scope("The city council passed this ordinance."), "local")

    def test_unclear_default(self):
        self.assertEqual(_classify_regulatory_scope("This affects businesses broadly."), "unclear")


class TestGuardrail(unittest.TestCase):
    def test_blocks_binding_ruling_request(self):
        reason = _no_issuing_binding_rulings(Task(input="Please issue an official ruling on this matter"))
        self.assertIsNotNone(reason)

    def test_allows_ordinary_question(self):
        self.assertIsNone(_no_issuing_binding_rulings(Task(input="How is this typically regulated?")))


class TestAgentIntegration(unittest.TestCase):
    def test_normal_task_completes(self):
        agent = build_government_public_policy_agent(_router(), model_override="mock-fast")
        result = agent.handle(Task(input="Summarize how this policy proposal would be implemented."))
        self.assertEqual(result.status, "completed")

    def test_binding_ruling_request_is_blocked(self):
        agent = build_government_public_policy_agent(_router(), model_override="mock-fast")
        result = agent.handle(Task(input="Please issue an official ruling on this matter"))
        self.assertEqual(result.status, "blocked")

    def test_declared_mcp_tool_raises_typed_error(self):
        agent = build_government_public_policy_agent(_router(), model_override="mock-fast")
        with self.assertRaises(MCPServerNotAvailableError):
            agent.tools.call("mcp:govinfo/search_legislation", "environmental policy")

    def test_knowledge_search_tool_is_callable(self):
        agent = build_government_public_policy_agent(_router(), model_override="mock-fast")
        results = agent.tools.call("search_policy_references", "what makes a sound policy analysis")
        self.assertTrue(results)

    def test_sub_agent_routing_to_policy_analyst(self):
        agent = build_government_public_policy_agent(_router(), model_override="mock-fast")
        role = agent.route_to_sub_agent_role(Task(input="Can the policy-analyst review this?"))
        self.assertEqual(role, "policy-analyst")


if __name__ == "__main__":
    unittest.main()
