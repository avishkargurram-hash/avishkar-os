import math
import unittest

from avishkar_knowledge import HashingEmbedder


class TestHashingEmbedder(unittest.TestCase):
    def test_vector_has_configured_dimensions(self):
        embedder = HashingEmbedder(dimensions=64)
        vector = embedder.embed("hello world")
        self.assertEqual(len(vector), 64)

    def test_vector_is_l2_normalized(self):
        embedder = HashingEmbedder(dimensions=64)
        vector = embedder.embed("the quick brown fox jumps")
        norm = math.sqrt(sum(v * v for v in vector))
        self.assertAlmostEqual(norm, 1.0, places=6)

    def test_deterministic_across_instances(self):
        # zlib.crc32 is stable across processes/runs, unlike Python's
        # built-in hash() for strings -- this is the property that makes
        # search results reproducible.
        a = HashingEmbedder(dimensions=64).embed("reproducibility matters")
        b = HashingEmbedder(dimensions=64).embed("reproducibility matters")
        self.assertEqual(a, b)

    def test_empty_text_is_zero_vector(self):
        embedder = HashingEmbedder(dimensions=32)
        vector = embedder.embed("   ")
        self.assertEqual(vector, tuple([0.0] * 32))

    def test_similar_text_scores_higher_than_dissimilar(self):
        from avishkar_knowledge.index import _cosine_similarity

        embedder = HashingEmbedder(dimensions=128)
        base = embedder.embed("the quick brown fox jumps over the lazy dog")
        similar = embedder.embed("a quick brown fox jumps over a lazy dog")
        different = embedder.embed("quantum mechanics and general relativity")

        self.assertGreater(_cosine_similarity(base, similar), _cosine_similarity(base, different))


if __name__ == "__main__":
    unittest.main()
