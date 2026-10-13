import unittest

from avishkar_layla.executors.ssrf_guard import unsafe_navigation_reason


class TestSSRFGuard(unittest.TestCase):
    def test_cloud_metadata_ip_is_blocked(self):
        reason = unsafe_navigation_reason("http://169.254.169.254/latest/meta-data/iam/security-credentials/")
        self.assertIsNotNone(reason)
        self.assertIn("169.254.169.254", reason)

    def test_gcp_metadata_hostname_is_blocked(self):
        reason = unsafe_navigation_reason("http://metadata.google.internal/computeMetadata/v1/")
        self.assertIsNotNone(reason)

    def test_localhost_hostname_is_blocked(self):
        reason = unsafe_navigation_reason("http://localhost:8080/admin")
        self.assertIsNotNone(reason)

    def test_loopback_ip_is_blocked(self):
        reason = unsafe_navigation_reason("http://127.0.0.1:9200/_cat/indices")
        self.assertIsNotNone(reason)

    def test_private_ip_ranges_are_blocked(self):
        for ip in ("10.0.0.1", "172.16.5.5", "192.168.1.1"):
            with self.subTest(ip=ip):
                self.assertIsNotNone(unsafe_navigation_reason(f"http://{ip}/"))

    def test_public_ip_is_allowed(self):
        self.assertIsNone(unsafe_navigation_reason("http://8.8.8.8/"))

    def test_data_url_is_never_blocked(self):
        self.assertIsNone(unsafe_navigation_reason("data:text/html,<h1>hi</h1>"))

    def test_about_blank_is_never_blocked(self):
        self.assertIsNone(unsafe_navigation_reason("about:blank"))

    def test_malformed_url_does_not_raise(self):
        # Doesn't need to be "safe" in any meaningful sense -- just
        # must not raise; the real navigation call will fail on its
        # own for a genuinely malformed URL.
        try:
            unsafe_navigation_reason("not a url at all :::")
        except Exception as exc:  # noqa: BLE001
            self.fail(f"unsafe_navigation_reason() raised for a malformed URL: {exc}")

    def test_unresolvable_hostname_does_not_raise_and_is_treated_as_unknown(self):
        # A real DNS lookup that will genuinely fail (invalid TLD) --
        # must not raise, and (since it can't be proven unsafe) is not
        # blocked by this guard; the real navigation attempt fails on
        # its own downstream.
        result = unsafe_navigation_reason("http://this-domain-genuinely-does-not-exist.invalid/")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
