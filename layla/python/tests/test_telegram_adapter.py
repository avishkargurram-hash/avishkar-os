"""TelegramChannelAdapter + TelegramBotAPITransport tests. Includes one
genuine network call to Telegram's real Bot API with a deliberately
invalid token -- proves the transport builds a real HTTP request and
parses a real error response. Zero side effects (an invalid token can
never send a real message). Skips gracefully if outbound network is
unavailable in this environment.
"""

import os
import unittest

from avishkar_integration import ProtocolInvocationError, RateLimit, RetryPolicy, ToolContract, ToolExecutionRequest, ToolRuntime, UniversalToolRegistry

from avishkar_layla.channels.telegram_adapter import TelegramBotAPITransport, TelegramChannelAdapter


def _contract() -> ToolContract:
    return ToolContract(
        identity="send-message", description="Send a Telegram message.", protocol="telegram",
        input_schema={"type": "object", "required": ["to", "body"]},
        rate_limit=RateLimit(requests_per_minute=30), retry_policy=RetryPolicy(max_attempts=1),
    )


class TestTelegramChannelAdapterWithFakeTransport(unittest.TestCase):
    def test_invoke_calls_the_transport_and_wraps_the_result(self):
        calls = []

        def fake_transport(to, body):
            calls.append((to, body))
            return "12345"

        adapter = TelegramChannelAdapter(tools=(_contract(),), transport=fake_transport)
        result = adapter.invoke(_contract(), ToolExecutionRequest(input={"to": "999", "body": "hi"}))

        self.assertEqual(result.status, "success")
        self.assertEqual(result.output["message_id"], "12345")
        self.assertEqual(calls, [("999", "hi")])

    def test_missing_to_field_raises(self):
        adapter = TelegramChannelAdapter(tools=(_contract(),), transport=lambda to, body: "x")
        with self.assertRaises(ProtocolInvocationError):
            adapter.invoke(_contract(), ToolExecutionRequest(input={"body": "hi"}))

    def test_unconfigured_transport_raises_adapter_ready(self):
        adapter = TelegramChannelAdapter(tools=(_contract(),))
        with self.assertRaises(ProtocolInvocationError) as ctx:
            adapter.invoke(_contract(), ToolExecutionRequest(input={"to": "999", "body": "hi"}))
        self.assertIn("ADAPTER READY", str(ctx.exception))

    def test_registers_with_the_real_universal_tool_registry(self):
        """Confirms Telegram routes through the existing MCP registry,
        not a second router.
        """
        registry = UniversalToolRegistry()
        adapter = TelegramChannelAdapter(tools=(_contract(),), transport=lambda to, body: "1")
        registry.register_adapter(adapter)
        runtime = ToolRuntime(registry, sleep_fn=lambda s: None)

        result = runtime.execute("telegram", "send-message", {"to": "999", "body": "hi"})
        self.assertEqual(result.status, "success")


class TestTelegramBotAPITransport(unittest.TestCase):
    def test_missing_token_raises_before_any_request(self):
        os.environ.pop("TEST_TELEGRAM_TOKEN", None)
        transport = TelegramBotAPITransport(token_env="TEST_TELEGRAM_TOKEN")
        with self.assertRaises(ProtocolInvocationError) as ctx:
            transport("999", "hi")
        self.assertIn("ADAPTER READY", str(ctx.exception))

    def test_real_request_with_an_invalid_token_gets_a_real_rejection(self):
        os.environ["TEST_TELEGRAM_TOKEN"] = "123456:not-a-real-token"
        try:
            transport = TelegramBotAPITransport(token_env="TEST_TELEGRAM_TOKEN")
            try:
                with self.assertRaises(ProtocolInvocationError) as ctx:
                    transport("999", "hi")
                self.assertTrue(
                    "401" in str(ctx.exception) or "Unauthorized" in str(ctx.exception) or "unauthorized" in str(ctx.exception).lower(),
                    f"expected a real Telegram Bot API rejection, got: {ctx.exception}",
                )
            except Exception as exc:  # noqa: BLE001
                if "failed" not in str(exc).lower():
                    raise
                self.skipTest(f"no outbound network access in this environment: {exc}")
        finally:
            os.environ.pop("TEST_TELEGRAM_TOKEN", None)


if __name__ == "__main__":
    unittest.main()
