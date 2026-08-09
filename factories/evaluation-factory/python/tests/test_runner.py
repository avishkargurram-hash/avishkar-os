import unittest

from avishkar_evaluation import (
    EmptyCaseSetError,
    EvalCase,
    EvalSuite,
    exact_match_scorer,
    passes_threshold,
    run_suite,
)


class TestRunSuite(unittest.TestCase):
    def test_averages_scores_across_cases(self):
        suite = EvalSuite(
            name="demo",
            cases=(
                EvalCase(inputs={"n": 1}, expected="one"),
                EvalCase(inputs={"n": 2}, expected="two"),
            ),
        )
        subjects = {1: "one", 2: "wrong"}

        report = run_suite(suite, lambda case: subjects[case.inputs["n"]], exact_match_scorer)

        self.assertEqual(report.scores, (1.0, 0.0))
        self.assertEqual(report.average, 0.5)

    def test_empty_suite_raises(self):
        suite = EvalSuite(name="empty", cases=())
        with self.assertRaises(EmptyCaseSetError):
            run_suite(suite, lambda case: "", exact_match_scorer)


class TestPassesThreshold(unittest.TestCase):
    def test_at_or_above_threshold_passes(self):
        suite = EvalSuite(name="demo", cases=(EvalCase(inputs={}, expected="x"),))
        report = run_suite(suite, lambda case: "x", exact_match_scorer)
        self.assertTrue(passes_threshold(report, 1.0))

    def test_below_threshold_fails(self):
        suite = EvalSuite(name="demo", cases=(EvalCase(inputs={}, expected="x"),))
        report = run_suite(suite, lambda case: "y", exact_match_scorer)
        self.assertFalse(passes_threshold(report, 0.5))


if __name__ == "__main__":
    unittest.main()
