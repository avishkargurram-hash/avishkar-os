import tempfile
import unittest
from pathlib import Path

from avishkar_agent import MCPServerNotAvailableError, Task
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router

from human_development_psychology_agent import (
    _crisis_escalation,
    _detect_crisis_language,
    _suggest_reflection_prompt,
    build_human_development_psychology_agent,
    load_blueprint,
)


def _router(response_text: str = "A therapist or counselor can help you go deeper on this.") -> Router:
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
        self.assertEqual(blueprint.name, "human-development-psychology")
        self.assertIn("crisis-resource-router", blueprint.sub_agent_roles)


class TestDetectCrisisLanguageTool(unittest.TestCase):
    def test_detects_crisis_phrase(self):
        self.assertTrue(_detect_crisis_language("I've been feeling suicidal lately."))

    def test_ordinary_text_is_not_crisis(self):
        self.assertFalse(_detect_crisis_language("I've been feeling stressed about work."))


class TestSuggestReflectionPromptTool(unittest.TestCase):
    def test_known_topic_returns_specific_prompt(self):
        prompt = _suggest_reflection_prompt("stress")
        self.assertIn("control", prompt)

    def test_unknown_topic_returns_generic_prompt(self):
        prompt = _suggest_reflection_prompt("something unusual")
        self.assertTrue(prompt)


class TestCrisisEscalationGuardrail(unittest.TestCase):
    def test_blocks_with_real_crisis_resource_info(self):
        reason = _crisis_escalation(Task(input="I want to end my life"))
        self.assertIsNotNone(reason)
        self.assertIn("988", reason)

    def test_allows_ordinary_question(self):
        self.assertIsNone(_crisis_escalation(Task(input="How can I communicate better with my partner?")))


class TestAgentIntegration(unittest.TestCase):
    def _agent(self, tmp):
        return build_human_development_psychology_agent(_router(), model_override="mock-fast", memory_root_dir=Path(tmp))

    def test_normal_task_completes(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._agent(tmp).handle(Task(input="How can I communicate better with my partner?"))
            self.assertEqual(result.status, "completed")

    def test_crisis_language_is_blocked_with_resource_info(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._agent(tmp).handle(Task(input="I want to end my life"))
            self.assertEqual(result.status, "blocked")
            self.assertIn("988", result.blocked_reason)

    def test_declared_mcp_tool_raises_typed_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(MCPServerNotAvailableError):
                self._agent(tmp).tools.call("mcp:psychology-today/find_local_therapist", "anxiety")

    def test_knowledge_search_tool_is_callable(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = self._agent(tmp).tools.call("search_growth_resources", "how does active listening work")
            self.assertTrue(results)

    def test_sub_agent_routing_to_communication_coach(self):
        with tempfile.TemporaryDirectory() as tmp:
            role = self._agent(tmp).route_to_sub_agent_role(Task(input="Can the communication-coach help with this?"))
            self.assertEqual(role, "communication-coach")


if __name__ == "__main__":
    unittest.main()
