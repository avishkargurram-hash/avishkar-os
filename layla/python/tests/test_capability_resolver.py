import unittest

from avishkar_layla.capability_resolver import CapabilityResolver


class TestCapabilityResolver(unittest.TestCase):
    def setUp(self):
        self.resolver = CapabilityResolver({
            "medical-healthcare": "Medical & Healthcare",
            "finance-economics": "Finance & Economics",
            "legal-compliance": "Legal & Compliance",
        })

    def test_exact_name_match(self):
        self.assertEqual(self.resolver.match("medical-healthcare"), ("medical-healthcare",))

    def test_exact_name_match_hyphen_insensitive(self):
        self.assertEqual(self.resolver.match("medical healthcare"), ("medical-healthcare",))

    def test_domain_substring_match(self):
        self.assertIn("finance-economics", self.resolver.match("finance"))

    def test_no_match_returns_empty_tuple(self):
        self.assertEqual(self.resolver.match("astrophysics"), ())

    def test_infer_relevant_does_not_false_positive_on_short_word_substrings(self):
        # Regression: "software-ai-engineering"'s "ai" name-word used to
        # be matched via substring, which false-positived inside
        # "domain" (cont-AI-ns "ai"). Whole-word tokenization fixed it;
        # this input deliberately contains "domain" and no real
        # reference to any known agent.
        self.assertEqual(self.resolver.infer_relevant("something with no domain keywords at all"), ())

    def test_infer_relevant_matches_whole_words(self):
        matches = self.resolver.infer_relevant("Build the software for this and get a legal review.")
        self.assertIn("legal-compliance", matches)
        self.assertNotIn("medical-healthcare", matches)


if __name__ == "__main__":
    unittest.main()
