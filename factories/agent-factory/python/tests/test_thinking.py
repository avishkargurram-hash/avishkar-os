import unittest

from avishkar_agent import DEFAULT_THINKING_MODELS, Task
from avishkar_agent.thinking import DECISION_MATRIX, FIRST_PRINCIPLES, SCIENTIFIC_METHOD, SYSTEMS_THINKING


def _task(**kwargs):
    kwargs.setdefault("input", "design a caching layer")
    return Task(**kwargs)


class TestDefaultThinkingModels(unittest.TestCase):
    def test_four_default_models_registered(self):
        names = {tm.name for tm in DEFAULT_THINKING_MODELS}
        self.assertEqual(names, {"first_principles", "systems_thinking", "scientific_method", "decision_matrix"})

    def test_first_principles_mentions_task_input(self):
        step = FIRST_PRINCIPLES.apply(_task(), {})
        self.assertEqual(step.strategy, "first_principles")
        self.assertIn("caching layer", step.content)

    def test_systems_thinking_mentions_task_input(self):
        step = SYSTEMS_THINKING.apply(_task(), {})
        self.assertEqual(step.strategy, "systems_thinking")
        self.assertIn("caching layer", step.content)

    def test_scientific_method_mentions_task_input(self):
        step = SCIENTIFIC_METHOD.apply(_task(), {})
        self.assertEqual(step.strategy, "scientific_method")
        self.assertIn("caching layer", step.content)

    def test_decision_matrix_uses_default_criteria(self):
        step = DECISION_MATRIX.apply(_task(), {})
        self.assertIn("correctness", step.content)
        self.assertIn("cost", step.content)

    def test_decision_matrix_uses_context_criteria_override(self):
        step = DECISION_MATRIX.apply(_task(), {"decision_criteria": ("latency", "safety")})
        self.assertIn("latency", step.content)
        self.assertIn("safety", step.content)
        self.assertNotIn("correctness", step.content)


if __name__ == "__main__":
    unittest.main()
