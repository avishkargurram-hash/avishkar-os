import tempfile
import unittest
from pathlib import Path

from avishkar_agent import MCPServerNotAvailableError, Task
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router

from education_knowledge_agent import (
    _check_learning_objective_format,
    _estimate_reading_level,
    _no_issuing_official_grades,
    build_education_knowledge_agent,
    load_blueprint,
)


def _router(response_text: str = "Ask your instructor to confirm the final grading criteria.") -> Router:
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
        self.assertEqual(blueprint.name, "education-knowledge")
        self.assertIn("tutor", blueprint.sub_agent_roles)


class TestEstimateReadingLevelTool(unittest.TestCase):
    def test_simple_short_text_is_elementary(self):
        self.assertEqual(_estimate_reading_level("The cat sat. It was red. It ran fast."), "elementary")

    def test_empty_text_is_unclear(self):
        self.assertEqual(_estimate_reading_level(""), "unclear")

    def test_complex_long_sentences_are_advanced(self):
        text = (
            "The multifaceted epistemological ramifications of this methodological "
            "approach necessitate a comprehensive interdisciplinary reevaluation "
            "of our foundational theoretical presuppositions regarding causality."
        )
        self.assertEqual(_estimate_reading_level(text), "advanced")


class TestCheckLearningObjectiveFormatTool(unittest.TestCase):
    def test_detects_blooms_verb(self):
        self.assertTrue(_check_learning_objective_format("Students will analyze the causes of the event."))

    def test_missing_verb_returns_false(self):
        self.assertFalse(_check_learning_objective_format("Students will know about the event."))


class TestGuardrail(unittest.TestCase):
    def test_blocks_official_grade_request(self):
        reason = _no_issuing_official_grades(Task(input="Please issue the official grade for this student"))
        self.assertIsNotNone(reason)

    def test_allows_ordinary_question(self):
        self.assertIsNone(_no_issuing_official_grades(Task(input="How should I structure this lesson?")))


class TestAgentIntegration(unittest.TestCase):
    def _agent(self, tmp):
        return build_education_knowledge_agent(_router(), model_override="mock-fast", memory_root_dir=Path(tmp))

    def test_normal_task_completes(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._agent(tmp).handle(Task(input="Help me write a learning objective for this unit."))
            self.assertEqual(result.status, "completed")

    def test_official_grade_request_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._agent(tmp).handle(Task(input="Please issue the official grade for this student"))
            self.assertEqual(result.status, "blocked")

    def test_declared_mcp_tool_raises_typed_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(MCPServerNotAvailableError):
                self._agent(tmp).tools.call("mcp:openstax/search_resources", "algebra basics")

    def test_knowledge_search_tool_is_callable(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = self._agent(tmp).tools.call("search_curriculum_resources", "how to design a curriculum")
            self.assertTrue(results)

    def test_sub_agent_routing_to_tutor(self):
        with tempfile.TemporaryDirectory() as tmp:
            role = self._agent(tmp).route_to_sub_agent_role(Task(input="Can the tutor explain this again?"))
            self.assertEqual(role, "tutor")


if __name__ == "__main__":
    unittest.main()
