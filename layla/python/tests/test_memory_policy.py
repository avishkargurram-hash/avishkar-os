import unittest

from avishkar_agent import InMemoryMemoryPolicy

from avishkar_layla import LaylaMemoryPolicy, MemoryPolicyViolationError


class TestLaylaMemoryPolicy(unittest.TestCase):
    def test_remember_and_recall_round_trips(self):
        policy = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        policy.remember("semantic", "favorite-editor", "vim", confidence=0.9, provenance="user", importance="low")

        record = policy.recall("semantic", "favorite-editor")

        self.assertEqual(record.value, "vim")
        self.assertEqual(record.confidence, 0.9)
        self.assertEqual(record.provenance, "user")
        self.assertEqual(record.importance, "low")
        self.assertTrue(record.stored_at)

    def test_recall_missing_key_returns_none(self):
        policy = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        self.assertIsNone(policy.recall("semantic", "nope"))

    def test_disallowed_kind_raises(self):
        policy = LaylaMemoryPolicy(InMemoryMemoryPolicy(), allowed_kinds=("semantic",))
        with self.assertRaises(MemoryPolicyViolationError):
            policy.remember("episodic", "k", "v")

    def test_secret_shaped_value_is_refused_even_at_low_importance(self):
        policy = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        with self.assertRaises(MemoryPolicyViolationError):
            policy.remember("semantic", "creds", "AKIAIOSFODNN7EXAMPLE", importance="low")

    def test_secret_shaped_value_nested_in_dict_is_refused(self):
        policy = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        with self.assertRaises(MemoryPolicyViolationError):
            policy.remember("semantic", "note", {"body": "key is AKIAIOSFODNN7EXAMPLE"})

    def test_forget_is_always_allowed_even_outside_allowed_kinds(self):
        backend = InMemoryMemoryPolicy()
        backend.remember("episodic", "k", {"value": "v", "confidence": 1.0, "provenance": "user", "importance": "normal", "stored_at": ""})
        policy = LaylaMemoryPolicy(backend, allowed_kinds=("semantic",))
        policy.forget("episodic", "k")  # must not raise
        self.assertIsNone(backend.recall("episodic", "k"))

    def test_correct_updates_value_and_records_provenance(self):
        policy = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        policy.remember("semantic", "timezone", "PST")

        corrected = policy.correct("semantic", "timezone", "EST", reason="user moved")

        self.assertEqual(corrected.value, "EST")
        self.assertIn("user moved", corrected.provenance)

    def test_sqlite_backend_round_trip(self):
        from avishkar_memory import SQLiteMemoryPolicy

        policy = LaylaMemoryPolicy(SQLiteMemoryPolicy(":memory:"))
        policy.remember("long_term", "k", {"nested": [1, 2, 3]}, importance="high")

        record = policy.recall("long_term", "k")

        self.assertEqual(record.value, {"nested": [1, 2, 3]})
        self.assertEqual(record.importance, "high")


if __name__ == "__main__":
    unittest.main()
