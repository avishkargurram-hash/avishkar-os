import unittest

from avishkar_agent import InMemoryMemoryPolicy


class TestInMemoryMemoryPolicy(unittest.TestCase):
    def test_remember_and_recall(self):
        memory = InMemoryMemoryPolicy()
        memory.remember("short_term", "last_task", "fix the bug")

        self.assertEqual(memory.recall("short_term", "last_task"), "fix the bug")

    def test_recall_missing_key_returns_none(self):
        memory = InMemoryMemoryPolicy()
        self.assertIsNone(memory.recall("long_term", "nonexistent"))

    def test_forget_removes_key(self):
        memory = InMemoryMemoryPolicy()
        memory.remember("episodic", "event-1", {"what": "deployed v2"})
        memory.forget("episodic", "event-1")

        self.assertIsNone(memory.recall("episodic", "event-1"))

    def test_kinds_are_isolated(self):
        memory = InMemoryMemoryPolicy()
        memory.remember("short_term", "key", "short")
        memory.remember("long_term", "key", "long")

        self.assertEqual(memory.recall("short_term", "key"), "short")
        self.assertEqual(memory.recall("long_term", "key"), "long")

    def test_unknown_kind_raises(self):
        memory = InMemoryMemoryPolicy()
        with self.assertRaises(ValueError):
            memory.remember("made_up_kind", "key", "value")

    def test_all_four_kinds_supported(self):
        memory = InMemoryMemoryPolicy()
        for kind in ("short_term", "long_term", "episodic", "semantic"):
            memory.remember(kind, "k", kind)
            self.assertEqual(memory.recall(kind, "k"), kind)


if __name__ == "__main__":
    unittest.main()
