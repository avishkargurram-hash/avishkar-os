import tempfile
import unittest
from pathlib import Path

from avishkar_agent import InMemoryMemoryPolicy, MemoryPolicyConfig
from avishkar_memory import FileMemoryPolicy, SQLiteMemoryPolicy, UnknownBackendError, build_memory_policy


class TestBuildMemoryPolicy(unittest.TestCase):
    def test_in_memory_backend(self):
        policy = build_memory_policy(MemoryPolicyConfig(backend="in_memory"))
        self.assertIsInstance(policy, InMemoryMemoryPolicy)

    def test_file_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy = build_memory_policy(MemoryPolicyConfig(backend="file"), root_dir=Path(tmp))
            self.assertIsInstance(policy, FileMemoryPolicy)
            policy.remember("short_term", "k", "v")
            self.assertEqual(policy.recall("short_term", "k"), "v")

    def test_sqlite_backend(self):
        policy = build_memory_policy(MemoryPolicyConfig(backend="sqlite"))
        self.assertIsInstance(policy, SQLiteMemoryPolicy)

    def test_unknown_backend_raises(self):
        with self.assertRaises(UnknownBackendError):
            build_memory_policy(MemoryPolicyConfig(backend="carrier-pigeon"))


if __name__ == "__main__":
    unittest.main()
