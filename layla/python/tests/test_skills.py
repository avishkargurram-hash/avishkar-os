import unittest

from avishkar_agent import InMemoryMemoryPolicy
from avishkar_evaluation import EvalCase, EvalSuite, exact_match_scorer

from avishkar_layla import LaylaMemoryPolicy
from avishkar_layla.skills import SKILL_APPROVED, SKILL_CANDIDATE, SKILL_REJECTED, SKILL_RETIRED, SkillNotFoundError, SkillRegistry


def _registry():
    return SkillRegistry(LaylaMemoryPolicy(InMemoryMemoryPolicy()))


class TestSkillRegistryPropose(unittest.TestCase):
    def test_propose_creates_a_candidate(self):
        registry = _registry()
        skill = registry.propose("daily-brief", "summarize the day", "research-agent", "Summarize today for {user}")

        self.assertEqual(skill.status, SKILL_CANDIDATE)
        self.assertEqual(skill.version, 1)
        self.assertIsNone(skill.eval_average)

    def test_get_missing_returns_none(self):
        registry = _registry()
        self.assertIsNone(registry.get("never-existed"))

    def test_execution_on_missing_skill_raises(self):
        registry = _registry()
        with self.assertRaises(SkillNotFoundError):
            registry.record_execution("nope", success=True)


class TestSkillRegistryEvaluation(unittest.TestCase):
    def test_a_passing_evaluation_approves_the_skill(self):
        registry = _registry()
        skill = registry.propose("greeting", "say hello", "research-agent", "Greet {user}")
        suite = EvalSuite(name="greeting-suite", cases=(EvalCase(inputs={}, expected="hello"),))

        result = registry.evaluate(skill.id, suite, subject_fn=lambda case: "hello", scorer=exact_match_scorer, threshold=0.5)

        self.assertEqual(result.status, SKILL_APPROVED)
        self.assertEqual(result.eval_average, 1.0)
        self.assertEqual(result.eval_case_count, 1)
        self.assertIn(result.id, {s.id for s in registry.list_approved()})

    def test_a_failing_evaluation_rejects_the_skill(self):
        registry = _registry()
        skill = registry.propose("greeting", "say hello", "research-agent", "Greet {user}")
        suite = EvalSuite(name="greeting-suite", cases=(EvalCase(inputs={}, expected="hello"),))

        result = registry.evaluate(skill.id, suite, subject_fn=lambda case: "goodbye", scorer=exact_match_scorer, threshold=0.5)

        self.assertEqual(result.status, SKILL_REJECTED)
        self.assertEqual(result.eval_average, 0.0)
        self.assertEqual(registry.list_approved(), ())

    def test_evaluate_unknown_skill_raises(self):
        registry = _registry()
        suite = EvalSuite(name="x", cases=(EvalCase(inputs={}, expected="y"),))
        with self.assertRaises(SkillNotFoundError):
            registry.evaluate("nope", suite, subject_fn=lambda case: "y", scorer=exact_match_scorer)


class TestSkillRegistryLifecycle(unittest.TestCase):
    def test_record_execution_tracks_counts(self):
        registry = _registry()
        skill = registry.propose("greeting", "say hello", "research-agent", "Greet {user}")

        registry.record_execution(skill.id, success=True)
        result = registry.record_execution(skill.id, success=False)

        self.assertEqual(result.execution_count, 2)
        self.assertEqual(result.success_count, 1)

    def test_retire_changes_status_and_removes_from_approved(self):
        registry = _registry()
        skill = registry.propose("greeting", "say hello", "research-agent", "Greet {user}")
        suite = EvalSuite(name="s", cases=(EvalCase(inputs={}, expected="hello"),))
        registry.evaluate(skill.id, suite, subject_fn=lambda case: "hello", scorer=exact_match_scorer, threshold=0.5)

        registry.retire(skill.id)

        self.assertEqual(registry.get(skill.id).status, SKILL_RETIRED)
        self.assertEqual(registry.list_approved(), ())

    def test_resolve_for_capability_only_returns_approved(self):
        registry = _registry()
        approved = registry.propose("a", "x", "finance-agent", "t")
        rejected = registry.propose("b", "x", "finance-agent", "t")
        suite = EvalSuite(name="s", cases=(EvalCase(inputs={}, expected="ok"),))
        registry.evaluate(approved.id, suite, subject_fn=lambda case: "ok", scorer=exact_match_scorer, threshold=0.5)
        registry.evaluate(rejected.id, suite, subject_fn=lambda case: "bad", scorer=exact_match_scorer, threshold=0.5)

        resolved = registry.resolve_for_capability("finance-agent")

        self.assertEqual({s.id for s in resolved}, {approved.id})


if __name__ == "__main__":
    unittest.main()
