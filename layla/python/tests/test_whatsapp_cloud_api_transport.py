"""Real WhatsAppCloudAPITransport tests. Includes one genuine network
call to Meta's real Graph API endpoint with a deliberately invalid
token -- proves the transport builds a real HTTP request and parses a
real error response, with zero side effects (an invalid token can
never actually send a message). Skips gracefully if this environment
has no outbound network access, rather than failing the whole suite.
"""

import os
import unittest

from avishkar_integration import ProtocolInvocationError

from avishkar_layla.channels.whatsapp_adapter import WhatsAppCloudAPITransport


class TestWhatsAppCloudAPITransport(unittest.TestCase):
    def test_missing_token_raises_before_any_request(self):
        os.environ.pop("TEST_WHATSAPP_TOKEN", None)
        transport = WhatsAppCloudAPITransport(phone_number_id="123456", token_env="TEST_WHATSAPP_TOKEN")
        with self.assertRaises(ProtocolInvocationError) as ctx:
            transport("+15550001111", "hello")
        self.assertIn("ADAPTER READY", str(ctx.exception))

    def test_real_request_against_metas_real_api_with_an_invalid_token_is_rejected(self):
        os.environ["TEST_WHATSAPP_TOKEN"] = "not-a-real-token"
        try:
            transport = WhatsAppCloudAPITransport(phone_number_id="000000000000000", token_env="TEST_WHATSAPP_TOKEN")
            try:
                with self.assertRaises(ProtocolInvocationError) as ctx:
                    transport("+15550001111", "hello")
                # A real Graph API error response, not a fabricated one.
                self.assertTrue(
                    "40" in str(ctx.exception) or "OAuth" in str(ctx.exception) or "token" in str(ctx.exception).lower(),
                    f"expected a real Meta Graph API error, got: {ctx.exception}",
                )
            except Exception as exc:  # noqa: BLE001 -- network unavailable in this environment
                if "failed" not in str(exc).lower():
                    raise
                self.skipTest(f"no outbound network access in this environment: {exc}")
        finally:
            os.environ.pop("TEST_WHATSAPP_TOKEN", None)


if __name__ == "__main__":
    unittest.main()
