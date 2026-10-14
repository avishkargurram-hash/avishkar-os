import tempfile
import unittest
from pathlib import Path

from avishkar_security import redact_secrets, scan_for_secrets, scan_repository_for_secrets

# All fixtures below are well-known-fake or synthetically invalid --
# AKIAIOSFODNN7EXAMPLE is AWS's own public documentation placeholder;
# the rest use an obvious "EXAMPLE"/"FAKE" marker instead of any real
# secret shape.


class TestScanForSecrets(unittest.TestCase):
    def test_detects_aws_access_key(self):
        matches = scan_for_secrets("aws_key = AKIAIOSFODNN7EXAMPLE")
        self.assertEqual({m.pattern_name for m in matches}, {"aws_access_key_id"})

    def test_detects_anthropic_style_key(self):
        matches = scan_for_secrets("ANTHROPIC_API_KEY=sk-ant-FAKE00000000000000000000")
        self.assertIn("anthropic_api_key", {m.pattern_name for m in matches})

    def test_detects_generic_api_key_assignment(self):
        matches = scan_for_secrets('api_key = "EXAMPLE1234567890abcdef"')
        self.assertIn("generic_api_key_assignment", {m.pattern_name for m in matches})

    def test_detects_private_key_header(self):
        matches = scan_for_secrets("-----BEGIN RSA PRIVATE KEY-----\nEXAMPLE\n-----END RSA PRIVATE KEY-----")
        self.assertIn("private_key_header", {m.pattern_name for m in matches})

    def test_detects_bearer_token(self):
        matches = scan_for_secrets("Authorization: Bearer EXAMPLE1234567890abcdefxyz")
        self.assertIn("generic_bearer_token", {m.pattern_name for m in matches})

    def test_ordinary_text_has_no_matches(self):
        matches = scan_for_secrets("This is a completely ordinary sentence about deploying software.")
        self.assertEqual(matches, ())

    def test_preview_never_contains_the_full_secret(self):
        secret = "AKIAIOSFODNN7EXAMPLE"
        matches = scan_for_secrets(secret)
        self.assertNotIn(secret, matches[0].preview)
        self.assertTrue(matches[0].preview.startswith(secret[:6]))


class TestRedactSecrets(unittest.TestCase):
    def test_redacts_every_match(self):
        text = "key=AKIAIOSFODNN7EXAMPLE and nothing else"
        redacted = redact_secrets(text)
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", redacted)
        self.assertIn("[REDACTED:aws_access_key_id]", redacted)

    def test_redacts_multiple_matches_correctly(self):
        text = "AKIAIOSFODNN7EXAMPLE ... sk-ant-FAKE00000000000000000000"
        redacted = redact_secrets(text)
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", redacted)
        self.assertNotIn("sk-ant-FAKE00000000000000000000", redacted)

    def test_text_with_no_secrets_is_unchanged(self):
        text = "ordinary text"
        self.assertEqual(redact_secrets(text), text)


class TestScanRepositoryForSecrets(unittest.TestCase):
    def test_finds_secret_in_a_real_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config.py").write_text("aws_key = 'AKIAIOSFODNN7EXAMPLE'", encoding="utf-8")
            (root / "readme.md").write_text("Nothing sensitive here.", encoding="utf-8")

            findings = scan_repository_for_secrets(root)

            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].path.name, "config.py")
            self.assertEqual(findings[0].match.pattern_name, "aws_access_key_id")

    def test_excludes_configured_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "__pycache__").mkdir()
            (root / "__pycache__" / "cached.py").write_text("AKIAIOSFODNN7EXAMPLE", encoding="utf-8")

            findings = scan_repository_for_secrets(root)

            self.assertEqual(findings, ())

    def test_ignores_extensions_not_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "secret.bin").write_text("AKIAIOSFODNN7EXAMPLE", encoding="utf-8")

            findings = scan_repository_for_secrets(root, extensions=(".py",))

            self.assertEqual(findings, ())


if __name__ == "__main__":
    unittest.main()
