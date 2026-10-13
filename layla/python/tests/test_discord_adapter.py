"""DiscordChannelAdapter + DiscordBotAPITransport tests. Includes one
genuine network call to Discord's real Bot REST API with a
deliberately invalid token -- proves the transport builds a real HTTP
request and parses a real error response. Zero side effects. Skips
gracefully if outbound network is unavailable in this environment.
"""

import os
import unittest

from avishkar_integration import ProtocolInvocationError, RateLimit, RetryPolicy, ToolContract, ToolExecutionRequest, ToolRuntime, UniversalToolRegistry

from avishkar_layla.channels.discord_adapter import DiscordBotAPITransport, DiscordChannelAdapter


def _contract() -> ToolContract:
    return ToolContract(
        identity="send-message", description="Send a Discord message.", protocol="discord",
        input_schema={"type": "object", "required": ["to", "body"]},
        rate_limit=RateLimit(requests_per_minute=30), retry_policy=RetryPolicy(max_attempts=1),
    )


class TestDiscordChannelAdapterWithFakeTransport(unittest.TestCase):
    def test_invoke_calls_the_transport_and_wraps_the_result(self):
        calls = []

        def fake_transport(to, body):
            calls.append((to, body))
            return "999888777"

        adapter = DiscordChannelAdapter(tools=(_contract(),), transport=fake_transport)
        result = adapter.invoke(_contract(), ToolExecutionRequest(input={"to": "12345", "body": "hi"}))

        self.assertEqual(result.status, "success")
        self.assertEqual(result.output["message_id"], "999888777")
        self.assertEqual(calls, [("12345", "hi")])

    def test_missing_to_field_raises(self):
        adapter = DiscordChannelAdapter(tools=(_contract(),), transport=lambda to, body: "x")
        with self.assertRaises(ProtocolInvocationError):
            adapter.invoke(_contract(), ToolExecutionRequest(input={"body": "hi"}))

    def test_unconfigured_transport_raises_adapter_ready(self):
        adapter = DiscordChannelAdapter(tools=(_contract(),))
        with self.assertRaises(ProtocolInvocationError) as ctx:
            adapter.invoke(_contract(), ToolExecutionRequest(input={"to": "12345", "body": "hi"}))
        self.assertIn("ADAPTER READY", str(ctx.exception))

    def test_registers_with_the_real_universal_tool_registry(self):
        registry = UniversalToolRegistry()
        adapter = DiscordChannelAdapter(tools=(_contract(),), transport=lambda to, body: "1")
        registry.register_adapter(adapter)
        runtime = ToolRuntime(registry, sleep_fn=lambda s: None)

        result = runtime.execute("discord", "send-message", {"to": "12345", "body": "hi"})
        self.assertEqual(result.status, "success")


class TestDiscordBotAPITransport(unittest.TestCase):
    def test_missing_token_raises_before_any_request(self):
        os.environ.pop("TEST_DISCORD_TOKEN", None)
        transport = DiscordBotAPITransport(token_env="TEST_DISCORD_TOKEN")
        with self.assertRaises(ProtocolInvocationError) as ctx:
            transport("12345", "hi")
        self.assertIn("ADAPTER READY", str(ctx.exception))

    def test_real_request_with_an_invalid_token_gets_a_real_rejection(self):
        os.environ["TEST_DISCORD_TOKEN"] = "not-a-real-token"
        try:
            transport = DiscordBotAPITransport(token_env="TEST_DISCORD_TOKEN")
            try:
                with self.assertRaises(ProtocolInvocationError) as ctx:
                    transport("12345", "hi")
                self.assertTrue(
                    "401" in str(ctx.exception) or "authoriz" in str(ctx.exception).lower(),
                    f"expected a real Discord Bot API rejection, got: {ctx.exception}",
                )
            except Exception as exc:  # noqa: BLE001
                if "failed" not in str(exc).lower():
                    raise
                self.skipTest(f"no outbound network access in this environment: {exc}")
        finally:
            os.environ.pop("TEST_DISCORD_TOKEN", None)


if __name__ == "__main__":
    unittest.main()
