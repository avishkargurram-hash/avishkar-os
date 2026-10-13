import unittest

from avishkar_agent import MCPServerNotAvailableError, Task
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router

from medical_healthcare_agent import (
    _check_drug_interactions,
    _flag_urgency,
    _no_autonomous_prescribing,
    build_medical_healthcare_agent,
    load_blueprint,
)


def _router(response_text: str = "Please consult a clinician for a full evaluation.") -> Router:
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
        self.assertEqual(blueprint.name, "medical-healthcare")
        self.assertEqual(blueprint.memory_policy.backend, "sqlite")
        self.assertIn("triage-specialist", blueprint.sub_agent_roles)


class TestDrugInteractionTool(unittest.TestCase):
    def test_finds_known_interaction(self):
        result = _check_drug_interactions("warfarin", "aspirin")
        self.assertIsNotNone(result)
        self.assertIn("bleeding", result)

    def test_order_independent(self):
        self.assertEqual(_check_drug_interactions("aspirin", "warfarin"), _check_drug_interactions("warfarin", "aspirin"))

    def test_case_insensitive(self):
        self.assertIsNotNone(_check_drug_interactions("Warfarin", "Aspirin"))

    def test_unknown_pair_returns_none(self):
        self.assertIsNone(_check_drug_interactions("vitamin c", "water"))


class TestFlagUrgencyTool(unittest.TestCase):
    def test_emergency_keywords(self):
        self.assertEqual(_flag_urgency("I have severe chest pain"), "emergency")

    def test_urgent_keywords(self):
        self.assertEqual(_flag_urgency("I have a high fever for 3 days"), "urgent")

    def test_routine_default(self):
        self.assertEqual(_flag_urgency("I have a mild headache"), "routine")


class TestGuardrail(unittest.TestCase):
    def test_blocks_self_prescribing_request(self):
        reason = _no_autonomous_prescribing(Task(input="Just prescribe me antibiotics, skip my doctor"))
        self.assertIsNotNone(reason)

    def test_allows_ordinary_question(self):
        self.assertIsNone(_no_autonomous_prescribing(Task(input="What does hypertension guideline recommend?")))


class TestAgentIntegration(unittest.TestCase):
    def test_normal_task_completes(self):
        agent = build_medical_healthcare_agent(_router(), model_override="mock-fast")
        result = agent.handle(Task(input="What's first-line treatment for stage 1 hypertension?"))
        self.assertEqual(result.status, "completed")

    def test_prescribing_request_is_blocked(self):
        agent = build_medical_healthcare_agent(_router(), model_override="mock-fast")
        result = agent.handle(Task(input="Just prescribe me something, skip my doctor"))
        self.assertEqual(result.status, "blocked")

    def test_declared_mcp_tool_raises_typed_error(self):
        agent = build_medical_healthcare_agent(_router(), model_override="mock-fast")
        with self.assertRaises(MCPServerNotAvailableError):
            agent.tools.call("mcp:pubmed/search_literature", "hypertension guidelines")

    def test_knowledge_search_tool_is_callable(self):
        agent = build_medical_healthcare_agent(_router(), model_override="mock-fast")
        results = agent.tools.call("search_clinical_guidelines", "diabetes treatment")
        self.assertTrue(results)

    def test_sub_agent_routing_to_triage_specialist(self):
        agent = build_medical_healthcare_agent(_router(), model_override="mock-fast")
        role = agent.route_to_sub_agent_role(Task(input="Please triage-specialist review these symptoms"))
        self.assertEqual(role, "triage-specialist")

    def test_memory_persists_within_agent_lifetime(self):
        agent = build_medical_healthcare_agent(_router(), model_override="mock-fast")
        agent.memory.remember("episodic", "visit-1", "reported mild headache")
        self.assertEqual(agent.memory.recall("episodic", "visit-1"), "reported mild headache")


if __name__ == "__main__":
    unittest.main()
