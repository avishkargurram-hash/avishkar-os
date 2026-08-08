import unittest

from avishkar_knowledge import Chunk, DimensionMismatchError, VectorIndex


def _chunk(chunk_id="c1", text="hello") -> Chunk:
    return Chunk(document_id="doc-1", chunk_id=chunk_id, text=text, position=0)


class TestVectorIndex(unittest.TestCase):
    def test_add_and_search_returns_best_match_first(self):
        index = VectorIndex(dimensions=3)
        index.add(_chunk("a"), (1.0, 0.0, 0.0))
        index.add(_chunk("b"), (0.0, 1.0, 0.0))

        results = index.search((1.0, 0.0, 0.0), top_k=2)

        self.assertEqual(results[0].chunk.chunk_id, "a")
        self.assertAlmostEqual(results[0].score, 1.0)

    def test_top_k_limits_results(self):
        index = VectorIndex(dimensions=2)
        for i in range(5):
            index.add(_chunk(f"c{i}"), (1.0, 0.0))

        self.assertEqual(len(index.search((1.0, 0.0), top_k=3)), 3)

    def test_dimension_mismatch_raises(self):
        index = VectorIndex(dimensions=3)
        with self.assertRaises(DimensionMismatchError):
            index.add(_chunk(), (1.0, 0.0))

    def test_len_reflects_added_entries(self):
        index = VectorIndex(dimensions=2)
        index.add(_chunk("a"), (1.0, 0.0))
        index.add(_chunk("b"), (0.0, 1.0))
        self.assertEqual(len(index), 2)


if __name__ == "__main__":
    unittest.main()
