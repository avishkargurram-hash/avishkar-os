import tempfile
import unittest
from pathlib import Path

from avishkar_agent import MCPServerNotAvailableError, Task
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router

from legal_compliance_agent import (
    _check_citation_format,
    _flag_risky_clauses,
    _no_unauthorized_legal_advice,
    build_legal_compliance_agent,
    load_blueprint,
)


def _router(response_text: str = "Consult a licensed attorney to confirm before signing.") -> Router:
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
        self.assertEqual(blueprint.name, "legal-compliance")
        self.assertEqual(blueprint.memory_policy.backend, "file")
        self.assertIn("contract-reviewer", blueprint.sub_agent_roles)


class TestFlagRiskyClausesTool(unittest.TestCase):
    def test_flags_unlimited_liability(self):
        self.assertIn("unlimited_liability", _flag_risky_clauses("The vendor accepts unlimited liability."))

    def test_flags_auto_renewal_without_notice(self):
        self.assertIn(
            "auto_renewal_without_notice",
            _flag_risky_clauses("This agreement shall automatically renew each year."),
        )

    def test_does_not_flag_auto_renewal_with_notice(self):
        self.assertNotIn(
            "auto_renewal_without_notice",
            _flag_risky_clauses("This agreement shall automatically renew unless either party gives 30 days notice."),
        )

    def test_ordinary_clause_has_no_flags(self):
        self.assertEqual(_flag_risky_clauses("The parties agree to a term of two years."), [])


class TestCheckCitationFormatTool(unittest.TestCase):
    def test_detects_valid_looking_citation(self):
        self.assertTrue(_check_citation_format("As held in 410 U.S. 113, the court found..."))

    def test_no_citation_returns_false(self):
        self.assertFalse(_check_citation_format("This contract has no citations in it."))


class TestGuardrail(unittest.TestCase):
    def test_blocks_representation_request(self):
        reason = _no_unauthorized_legal_advice(Task(input="Please represent me in court next week"))
        self.assertIsNotNone(reason)

    def test_allows_ordinary_question(self):
        self.assertIsNone(_no_unauthorized_legal_advice(Task(input="What should an NDA's term typically be?")))


class TestAgentIntegration(unittest.TestCase):
    def _agent(self, tmp):
        return build_legal_compliance_agent(_router(), model_override="mock-fast", memory_root_dir=Path(tmp))

    def test_normal_task_completes(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = self._agent(tmp)
            result = agent.handle(Task(input="What should I check before signing an NDA?"))
            self.assertEqual(result.status, "completed")

    def test_representation_request_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = self._agent(tmp)
            result = agent.handle(Task(input="Please represent me in court next week"))
            self.assertEqual(result.status, "blocked")

    def test_declared_mcp_tool_raises_typed_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = self._agent(tmp)
            with self.assertRaises(MCPServerNotAvailableError):
                agent.tools.call("mcp:courtlistener/search_case_law", "landmark contract cases")

    def test_knowledge_search_tool_is_callable(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = self._agent(tmp)
            results = agent.tools.call("search_legal_references", "what should a contract review check")
            self.assertTrue(results)

    def test_sub_agent_routing_to_contract_reviewer(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = self._agent(tmp)
            role = agent.route_to_sub_agent_role(Task(input="Can the contract-reviewer look at this?"))
            self.assertEqual(role, "contract-reviewer")

    def test_memory_persists_across_agent_instances_on_same_root_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self._agent(tmp)
            first.memory.remember("long_term", "client-x-preference", "prefers arbitration clauses")

            second = self._agent(tmp)
            self.assertEqual(second.memory.recall("long_term", "client-x-preference"), "prefers arbitration clauses")


if __name__ == "__main__":
    unittest.main()
