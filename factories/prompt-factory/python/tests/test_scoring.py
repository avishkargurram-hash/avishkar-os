import unittest

from avishkar_prompt import (
    EvalCase,
    PromptRegistry,
    PromptVariable,
    PromptVersion,
    compare_versions,
    evaluate_version,
    exact_match_scorer,
    keyword_presence_scorer,
)


class TestExactMatchScorer(unittest.TestCase):
    def test_exact_match_scores_one(self):
        self.assertEqual(exact_match_scorer("Hello Ada", EvalCase(inputs={}, expected="Hello Ada")), 1.0)

    def test_mismatch_scores_zero(self):
        self.assertEqual(exact_match_scorer("Hello Ada", EvalCase(inputs={}, expected="Hi Ada")), 0.0)


class TestKeywordPresenceScorer(unittest.TestCase):
    def test_all_keywords_present_scores_one(self):
        case = EvalCase(inputs={}, expected=["test suite", "review"])
        score = keyword_presence_scorer("Requires a test suite and a code review.", case)
        self.assertEqual(score, 1.0)

    def test_partial_keywords_present_scores_proportionally(self):
        case = EvalCase(inputs={}, expected=["test suite", "sign-off"])
        score = keyword_presence_scorer("Requires a test suite only.", case)
        self.assertEqual(score, 0.5)

    def test_case_insensitive(self):
        case = EvalCase(inputs={}, expected=["TEST SUITE"])
        score = keyword_presence_scorer("requires a test suite", case)
        self.assertEqual(score, 1.0)

    def test_no_required_keywords_scores_one(self):
        self.assertEqual(keyword_presence_scorer("anything", EvalCase(inputs={}, expected=[])), 1.0)


class TestEvaluateVersion(unittest.TestCase):
    def test_averages_scores_across_cases(self):
        registry = PromptRegistry()
        registry.register(
            "greeting",
            PromptVersion(version="1.0.0", template="Hi {name}", variables=(PromptVariable(name="name"),)),
        )
        cases = [
            EvalCase(inputs={"name": "Ada"}, expected="Hi Ada"),
            EvalCase(inputs={"name": "Grace"}, expected="wrong"),
        ]

        report = evaluate_version(registry, "greeting", "1.0.0", cases, exact_match_scorer)

        self.assertEqual(report.scores, (1.0, 0.0))
        self.assertEqual(report.average, 0.5)

    def test_empty_cases_average_zero(self):
        registry = PromptRegistry()
        registry.register(
            "greeting",
            PromptVersion(version="1.0.0", template="Hi", variables=()),
        )
        report = evaluate_version(registry, "greeting", "1.0.0", [], exact_match_scorer)
        self.assertEqual(report.average, 0.0)


class TestCompareVersions(unittest.TestCase):
    def test_higher_average_is_improved(self):
        registry = PromptRegistry()
        registry.register(
            "greeting",
            PromptVersion(version="1.0.0", template="Hi {name}", variables=(PromptVariable(name="name"),)),
        )
        registry.register(
            "greeting",
            PromptVersion(version="2.0.0", template="Hello there, {name}!", variables=(PromptVariable(name="name"),)),
        )
        cases = [EvalCase(inputs={"name": "Ada"}, expected=["Hello", "Ada"])]

        report_a = evaluate_version(registry, "greeting", "1.0.0", cases, keyword_presence_scorer)
        report_b = evaluate_version(registry, "greeting", "2.0.0", cases, keyword_presence_scorer)
        result = compare_versions(report_a, report_b)

        self.assertTrue(result.improved)
        self.assertGreater(result.delta, 0)

    def test_equal_scores_are_not_improved(self):
        from avishkar_prompt import EvalReport

        result = compare_versions(EvalReport(scores=(1.0,), average=1.0), EvalReport(scores=(1.0,), average=1.0))
        self.assertFalse(result.improved)
        self.assertEqual(result.delta, 0.0)


if __name__ == "__main__":
    unittest.main()
