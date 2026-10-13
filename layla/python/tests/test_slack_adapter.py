"""SlackChannelAdapter + SlackWebAPITransport tests. Includes one
genuine network call to Slack's real Web API with a deliberately
invalid token -- proves the transport builds a real HTTP request and
correctly reads Slack's real `ok: false` error shape (Slack always
returns HTTP 200, even on failure). Zero side effects. Skips
gracefully if outbound network is unavailable in this environment.
"""

import os
import unittest

from avishkar_integration import ProtocolInvocationError, RateLimit, RetryPolicy, ToolContract, ToolExecutionRequest, ToolRuntime, UniversalToolRegistry

from avishkar_layla.channels.slack_adapter import SlackChannelAdapter, SlackWebAPITransport


def _contract() -> ToolContract:
    return ToolContract(
        identity="send-message", description="Send a Slack message.", protocol="slack",
        input_schema={"type": "object", "required": ["to", "body"]},
        rate_limit=RateLimit(requests_per_minute=30), retry_policy=RetryPolicy(max_attempts=1),
    )


class TestSlackChannelAdapterWithFakeTransport(unittest.TestCase):
    def test_invoke_calls_the_transport_and_wraps_the_result(self):
        calls = []

        def fake_transport(to, body):
            calls.append((to, body))
            return "1620000000.000100"

        adapter = SlackChannelAdapter(tools=(_contract(),), transport=fake_transport)
        result = adapter.invoke(_contract(), ToolExecutionRequest(input={"to": "#general", "body": "hi"}))

        self.assertEqual(result.status, "success")
        self.assertEqual(result.output["message_id"], "1620000000.000100")
        self.assertEqual(calls, [("#general", "hi")])

    def test_missing_to_field_raises(self):
        adapter = SlackChannelAdapter(tools=(_contract(),), transport=lambda to, body: "x")
        with self.assertRaises(ProtocolInvocationError):
            adapter.invoke(_contract(), ToolExecutionRequest(input={"body": "hi"}))

    def test_unconfigured_transport_raises_adapter_ready(self):
        adapter = SlackChannelAdapter(tools=(_contract(),))
        with self.assertRaises(ProtocolInvocationError) as ctx:
            adapter.invoke(_contract(), ToolExecutionRequest(input={"to": "#general", "body": "hi"}))
        self.assertIn("ADAPTER READY", str(ctx.exception))

    def test_registers_with_the_real_universal_tool_registry(self):
        registry = UniversalToolRegistry()
        adapter = SlackChannelAdapter(tools=(_contract(),), transport=lambda to, body: "1")
        registry.register_adapter(adapter)
        runtime = ToolRuntime(registry, sleep_fn=lambda s: None)

        result = runtime.execute("slack", "send-message", {"to": "#general", "body": "hi"})
        self.assertEqual(result.status, "success")


class TestSlackWebAPITransport(unittest.TestCase):
    def test_missing_token_raises_before_any_request(self):
        os.environ.pop("TEST_SLACK_TOKEN", None)
        transport = SlackWebAPITransport(token_env="TEST_SLACK_TOKEN")
        with self.assertRaises(ProtocolInvocationError) as ctx:
            transport("#general", "hi")
        self.assertIn("ADAPTER READY", str(ctx.exception))

    def test_real_request_with_an_invalid_token_gets_a_real_rejection(self):
        os.environ["TEST_SLACK_TOKEN"] = "xoxb-not-a-real-token"
        try:
            transport = SlackWebAPITransport(token_env="TEST_SLACK_TOKEN")
            try:
                with self.assertRaises(ProtocolInvocationError) as ctx:
                    transport("#general", "hi")
                self.assertTrue(
                    "auth" in str(ctx.exception).lower() or "token" in str(ctx.exception).lower(),
                    f"expected a real Slack Web API auth rejection, got: {ctx.exception}",
                )
            except Exception as exc:  # noqa: BLE001
                if "failed" not in str(exc).lower():
                    raise
                self.skipTest(f"no outbound network access in this environment: {exc}")
        finally:
            os.environ.pop("TEST_SLACK_TOKEN", None)


if __name__ == "__main__":
    unittest.main()
