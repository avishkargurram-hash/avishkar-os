import unittest

from avishkar_knowledge import EmptyDocumentError, chunk_text


class TestChunkText(unittest.TestCase):
    def test_short_text_is_one_chunk(self):
        chunks = chunk_text("doc-1", "the quick brown fox", chunk_size=10, overlap=2)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].text, "the quick brown fox")
        self.assertEqual(chunks[0].chunk_id, "doc-1#0")

    def test_long_text_splits_with_overlap(self):
        words = [f"word{i}" for i in range(20)]
        text = " ".join(words)
        chunks = chunk_text("doc-1", text, chunk_size=10, overlap=3)

        self.assertGreater(len(chunks), 1)
        # last 3 words of chunk 0 should reappear at the start of chunk 1
        chunk0_words = chunks[0].text.split()
        chunk1_words = chunks[1].text.split()
        self.assertEqual(chunk0_words[-3:], chunk1_words[:3])

    def test_positions_are_sequential(self):
        text = " ".join(f"w{i}" for i in range(30))
        chunks = chunk_text("doc-1", text, chunk_size=10, overlap=2)
        self.assertEqual([c.position for c in chunks], list(range(len(chunks))))

    def test_empty_text_raises(self):
        with self.assertRaises(EmptyDocumentError):
            chunk_text("doc-1", "   ")

    def test_chunk_size_must_exceed_overlap(self):
        with self.assertRaises(ValueError):
            chunk_text("doc-1", "some text here", chunk_size=5, overlap=5)


if __name__ == "__main__":
    unittest.main()
