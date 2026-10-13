import unittest

from platform_standards_kb import build_platform_standards_kb


class TestPlatformStandardsKB(unittest.TestCase):
    def test_ingests_all_five_documents(self):
        kb = build_platform_standards_kb()
        self.assertEqual(len(kb), 5)

    def test_search_finds_dry_principle_for_relevant_query(self):
        kb = build_platform_standards_kb()
        results = kb.search("does this already exist somewhere DRY reuse")
        self.assertEqual(results[0].chunk.document_id, "engineering-principles")

    def test_search_finds_security_checklist_for_relevant_query(self):
        kb = build_platform_standards_kb()
        results = kb.search("secrets credentials committed API keys")
        self.assertEqual(results[0].chunk.document_id, "security-checklist")

    def test_search_finds_naming_conventions_for_relevant_query(self):
        kb = build_platform_standards_kb()
        results = kb.search("kebab-case snake_case directory naming")
        self.assertEqual(results[0].chunk.document_id, "naming-conventions")


if __name__ == "__main__":
    unittest.main()
