import unittest

from avishkar_evaluation import EvalCase, length_bounds_scorer, weighted_keyword_scorer


class TestLengthBoundsScorer(unittest.TestCase):
    def test_within_bounds_scores_one(self):
        scorer = length_bounds_scorer(5, 10)
        self.assertEqual(scorer("hello!", EvalCase(inputs={})), 1.0)

    def test_too_short_scores_zero(self):
        scorer = length_bounds_scorer(5, 10)
        self.assertEqual(scorer("hi", EvalCase(inputs={})), 0.0)

    def test_too_long_scores_zero(self):
        scorer = length_bounds_scorer(5, 10)
        self.assertEqual(scorer("way too long a string", EvalCase(inputs={})), 0.0)


class TestWeightedKeywordScorer(unittest.TestCase):
    def test_all_keywords_present_scores_one(self):
        scorer = weighted_keyword_scorer({"policy": 2.0, "review": 1.0})
        self.assertEqual(scorer("per policy, needs a review", EvalCase(inputs={})), 1.0)

    def test_partial_keywords_weighted_by_importance(self):
        scorer = weighted_keyword_scorer({"policy": 3.0, "review": 1.0})
        # only "policy" present -- 3.0 / (3.0 + 1.0)
        self.assertEqual(scorer("per policy only", EvalCase(inputs={})), 0.75)

    def test_no_weights_scores_one(self):
        scorer = weighted_keyword_scorer({})
        self.assertEqual(scorer("anything", EvalCase(inputs={})), 1.0)

    def test_case_insensitive(self):
        scorer = weighted_keyword_scorer({"POLICY": 1.0})
        self.assertEqual(scorer("per policy", EvalCase(inputs={})), 1.0)


if __name__ == "__main__":
    unittest.main()
