import unittest

from avishkar_knowledge import KnowledgeBase


class TestKnowledgeBase(unittest.TestCase):
    def test_ingest_returns_chunks_and_indexes_them(self):
        kb = KnowledgeBase(chunk_size=10, overlap=2)
        chunks = kb.ingest("doc-1", " ".join(f"w{i}" for i in range(25)))

        self.assertGreater(len(chunks), 1)
        self.assertEqual(len(kb), len(chunks))

    def test_search_finds_relevant_document(self):
        kb = KnowledgeBase()
        kb.ingest("policy", "All deploys require a passing test suite and a code review.")
        kb.ingest("recipe", "Preheat the oven to 350 degrees and mix the flour with sugar.")

        results = kb.search("what do we require before deploying code")

        self.assertEqual(results[0].chunk.document_id, "policy")

    def test_search_respects_top_k(self):
        kb = KnowledgeBase(chunk_size=5, overlap=1)
        kb.ingest("doc-1", " ".join(f"w{i}" for i in range(50)))

        self.assertLessEqual(len(kb.search("w0 w1", top_k=2)), 2)

    def test_empty_index_returns_no_results(self):
        kb = KnowledgeBase()
        self.assertEqual(kb.search("anything"), ())


if __name__ == "__main__":
    unittest.main()
