import unittest

from avishkar_knowledge import KnowledgeBase, as_tool


class TestAsTool(unittest.TestCase):
    def test_wraps_search_as_a_callable_tool(self):
        kb = KnowledgeBase()
        kb.ingest("policy", "All deploys require a passing test suite.")
        tool = as_tool(kb)

        self.assertEqual(tool.name, "search_knowledge")
        results = tool.call("deploy requirements")
        self.assertTrue(results)
        self.assertIn("text", results[0])
        self.assertIn("score", results[0])

    def test_custom_name(self):
        kb = KnowledgeBase()
        tool = as_tool(kb, name="search_policies")
        self.assertEqual(tool.name, "search_policies")


if __name__ == "__main__":
    unittest.main()
