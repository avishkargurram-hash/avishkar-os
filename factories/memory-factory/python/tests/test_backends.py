"""Shared behavioral tests for every MemoryPolicy backend -- both real
backends must satisfy the identical contract (avishkar_agent.MemoryPolicy),
so one mixin drives both test classes rather than duplicating assertions.
"""

import tempfile
import unittest
from pathlib import Path

from avishkar_memory import FileMemoryPolicy, InvalidMemoryKindError, SQLiteMemoryPolicy


class _MemoryPolicyContractTests:
    """Mixin -- subclasses provide `self.policy`. Not collected directly
    by unittest (it doesn't subclass TestCase).
    """

    def test_remember_and_recall(self):
        self.policy.remember("short_term", "task", "fix the bug")
        self.assertEqual(self.policy.recall("short_term", "task"), "fix the bug")

    def test_recall_missing_key_returns_none(self):
        self.assertIsNone(self.policy.recall("long_term", "nonexistent"))

    def test_forget_removes_key(self):
        self.policy.remember("episodic", "event-1", {"what": "deployed v2"})
        self.policy.forget("episodic", "event-1")
        self.assertIsNone(self.policy.recall("episodic", "event-1"))

    def test_forget_missing_key_does_not_raise(self):
        self.policy.forget("semantic", "never-existed")  # must not raise

    def test_kinds_are_isolated(self):
        self.policy.remember("short_term", "key", "short")
        self.policy.remember("long_term", "key", "long")
        self.assertEqual(self.policy.recall("short_term", "key"), "short")
        self.assertEqual(self.policy.recall("long_term", "key"), "long")

    def test_unknown_kind_raises(self):
        with self.assertRaises(InvalidMemoryKindError):
            self.policy.remember("made_up_kind", "key", "value")

    def test_complex_values_round_trip(self):
        value = {"nested": {"list": [1, 2, 3], "flag": True}}
        self.policy.remember("semantic", "complex", value)
        self.assertEqual(self.policy.recall("semantic", "complex"), value)

    def test_overwrite_updates_value(self):
        self.policy.remember("short_term", "k", "first")
        self.policy.remember("short_term", "k", "second")
        self.assertEqual(self.policy.recall("short_term", "k"), "second")


class TestFileMemoryPolicy(_MemoryPolicyContractTests, unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.policy = FileMemoryPolicy(Path(self._tmpdir.name))

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_persists_across_new_instances_pointed_at_same_dir(self):
        self.policy.remember("long_term", "fact", "the sky is blue")
        reopened = FileMemoryPolicy(Path(self._tmpdir.name))
        self.assertEqual(reopened.recall("long_term", "fact"), "the sky is blue")

    def test_list_keys(self):
        self.policy.remember("short_term", "a", 1)
        self.policy.remember("short_term", "b", 2)
        self.assertEqual(set(self.policy.list_keys("short_term")), {"a", "b"})


class TestSQLiteMemoryPolicy(_MemoryPolicyContractTests, unittest.TestCase):
    def setUp(self):
        self.policy = SQLiteMemoryPolicy(":memory:")

    def tearDown(self):
        self.policy.close()

    def test_persists_across_connections_to_the_same_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "memory.sqlite3")
            first = SQLiteMemoryPolicy(db_path)
            first.remember("long_term", "fact", "water boils at 100C")
            first.close()

            second = SQLiteMemoryPolicy(db_path)
            self.assertEqual(second.recall("long_term", "fact"), "water boils at 100C")
            second.close()

    def test_list_keys(self):
        self.policy.remember("episodic", "a", 1)
        self.policy.remember("episodic", "b", 2)
        self.assertEqual(set(self.policy.list_keys("episodic")), {"a", "b"})


if __name__ == "__main__":
    unittest.main()
