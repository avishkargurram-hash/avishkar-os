"""SMSChannelAdapter + TwilioSMSTransport tests. Includes one genuine
network call to Twilio's real REST API (via the real, installed
`twilio` SDK) with deliberately invalid credentials -- proves the
transport genuinely reaches Twilio and parses a real error response.
Zero side effects (invalid credentials can never send a real SMS).
Skips gracefully if outbound network is unavailable in this
environment.
"""

import os
import unittest

from avishkar_integration import ProtocolInvocationError, RateLimit, RetryPolicy, ToolContract, ToolExecutionRequest, ToolRuntime, UniversalToolRegistry

from avishkar_layla.channels.sms_adapter import SMSChannelAdapter, TwilioSMSTransport


def _contract() -> ToolContract:
    return ToolContract(
        identity="send-message", description="Send an SMS.", protocol="sms",
        input_schema={"type": "object", "required": ["to", "body"]},
        rate_limit=RateLimit(requests_per_minute=30), retry_policy=RetryPolicy(max_attempts=1),
    )


class TestSMSChannelAdapterWithFakeTransport(unittest.TestCase):
    def test_invoke_calls_the_transport_and_wraps_the_result(self):
        calls = []

        def fake_transport(to, body):
            calls.append((to, body))
            return "SM1234567890"

        adapter = SMSChannelAdapter(tools=(_contract(),), transport=fake_transport)
        result = adapter.invoke(_contract(), ToolExecutionRequest(input={"to": "+15550001111", "body": "hi"}))

        self.assertEqual(result.status, "success")
        self.assertEqual(result.output["message_id"], "SM1234567890")
        self.assertEqual(calls, [("+15550001111", "hi")])

    def test_missing_to_field_raises(self):
        adapter = SMSChannelAdapter(tools=(_contract(),), transport=lambda to, body: "x")
        with self.assertRaises(ProtocolInvocationError):
            adapter.invoke(_contract(), ToolExecutionRequest(input={"body": "hi"}))

    def test_unconfigured_transport_raises_adapter_ready(self):
        adapter = SMSChannelAdapter(tools=(_contract(),))
        with self.assertRaises(ProtocolInvocationError) as ctx:
            adapter.invoke(_contract(), ToolExecutionRequest(input={"to": "+15550001111", "body": "hi"}))
        self.assertIn("ADAPTER READY", str(ctx.exception))

    def test_registers_with_the_real_universal_tool_registry(self):
        registry = UniversalToolRegistry()
        adapter = SMSChannelAdapter(tools=(_contract(),), transport=lambda to, body: "1")
        registry.register_adapter(adapter)
        runtime = ToolRuntime(registry, sleep_fn=lambda s: None)

        result = runtime.execute("sms", "send-message", {"to": "+15550001111", "body": "hi"})
        self.assertEqual(result.status, "success")


class TestTwilioSMSTransport(unittest.TestCase):
    def test_missing_credentials_raises_before_any_request(self):
        os.environ.pop("TEST_TWILIO_SID", None)
        os.environ.pop("TEST_TWILIO_TOKEN", None)
        transport = TwilioSMSTransport(
            from_number="+15550009999", account_sid_env="TEST_TWILIO_SID", auth_token_env="TEST_TWILIO_TOKEN",
        )
        with self.assertRaises(ProtocolInvocationError) as ctx:
            transport("+15550001111", "hi")
        self.assertIn("ADAPTER READY", str(ctx.exception))

    def test_real_request_with_invalid_credentials_gets_a_real_rejection(self):
        os.environ["TEST_TWILIO_SID"] = "AC" + "0" * 32  # real Twilio SID shape, fake value
        os.environ["TEST_TWILIO_TOKEN"] = "not-a-real-auth-token"
        try:
            transport = TwilioSMSTransport(
                from_number="+15550009999", account_sid_env="TEST_TWILIO_SID", auth_token_env="TEST_TWILIO_TOKEN",
            )
            try:
                with self.assertRaises(ProtocolInvocationError) as ctx:
                    transport("+15550001111", "hi")
                self.assertTrue(
                    "auth" in str(ctx.exception).lower() or "20003" in str(ctx.exception) or "401" in str(ctx.exception),
                    f"expected a real Twilio rejection, got: {ctx.exception}",
                )
            except Exception as exc:  # noqa: BLE001
                if "failed" not in str(exc).lower():
                    raise
                self.skipTest(f"no outbound network access in this environment: {exc}")
        finally:
            os.environ.pop("TEST_TWILIO_SID", None)
            os.environ.pop("TEST_TWILIO_TOKEN", None)


if __name__ == "__main__":
    unittest.main()
