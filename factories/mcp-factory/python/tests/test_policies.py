import unittest

from avishkar_integration import AccessControlPolicy, SecurityPolicy


class TestAccessControlPolicy(unittest.TestCase):
    def test_default_allows_everyone(self):
        policy = AccessControlPolicy()
        self.assertTrue(policy.is_allowed("anyone"))
        self.assertTrue(policy.is_allowed(None))

    def test_allowlist_restricts(self):
        policy = AccessControlPolicy(allowed_callers=("agent-a",))
        self.assertTrue(policy.is_allowed("agent-a"))
        self.assertFalse(policy.is_allowed("agent-b"))

    def test_denylist_overrides_allowlist(self):
        policy = AccessControlPolicy(allowed_callers=("agent-a",), denied_callers=("agent-a",))
        self.assertFalse(policy.is_allowed("agent-a"))


class TestSecurityPolicy(unittest.TestCase):
    def test_defaults_to_untrusted(self):
        policy = SecurityPolicy()
        self.assertEqual(policy.trust_level, "untrusted")

    def test_invalid_trust_level_raises(self):
        with self.assertRaises(ValueError):
            SecurityPolicy(trust_level="sort-of")


if __name__ == "__main__":
    unittest.main()
