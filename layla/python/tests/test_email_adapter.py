import unittest

from avishkar_integration import ProtocolInvocationError, RateLimit, RetryPolicy, ToolContract, ToolExecutionRequest, ToolRuntime, UniversalToolRegistry

from avishkar_layla.channels.email_adapter import EmailChannelAdapter


def _contract() -> ToolContract:
    return ToolContract(
        identity="send-update",
        description="Send a routine status update email.",
        protocol="email",
        input_schema={"type": "object", "required": ["to", "subject", "body"]},
        rate_limit=RateLimit(requests_per_minute=30),
        retry_policy=RetryPolicy(max_attempts=1),
    )


class TestEmailChannelAdapterUnconfigured(unittest.TestCase):
    def test_unconfigured_transport_raises_the_documented_boundary_error(self):
        adapter = EmailChannelAdapter(tools=(_contract(),))
        request = ToolExecutionRequest(input={"to": "user@example.com", "subject": "Hi", "body": "Update."})
        with self.assertRaises(ProtocolInvocationError) as ctx:
            adapter.invoke(_contract(), request)
        self.assertIn("ADAPTER READY", str(ctx.exception))


class TestEmailChannelAdapterWithFakeTransport(unittest.TestCase):
    def test_successful_send_returns_message_id(self):
        sent = []

        def fake_transport(to, subject, body):
            sent.append((to, subject, body))
            return "msg-123"

        adapter = EmailChannelAdapter(tools=(_contract(),), transport=fake_transport)
        request = ToolExecutionRequest(input={"to": "user@example.com", "subject": "Hi", "body": "Update."})

        result = adapter.invoke(_contract(), request)

        self.assertEqual(result.status, "success")
        self.assertEqual(result.output["message_id"], "msg-123")
        self.assertEqual(sent, [("user@example.com", "Hi", "Update.")])

    def test_missing_to_field_raises(self):
        adapter = EmailChannelAdapter(tools=(_contract(),), transport=lambda to, s, b: "x")
        request = ToolExecutionRequest(input={"subject": "Hi", "body": "Update."})
        with self.assertRaises(ProtocolInvocationError):
            adapter.invoke(_contract(), request)

    def test_transport_failure_is_normalized_into_protocol_invocation_error(self):
        def failing_transport(to, subject, body):
            raise RuntimeError("SMTP connection refused")

        adapter = EmailChannelAdapter(tools=(_contract(),), transport=failing_transport)
        request = ToolExecutionRequest(input={"to": "user@example.com", "subject": "Hi", "body": "x"})

        with self.assertRaises(ProtocolInvocationError):
            adapter.invoke(_contract(), request)

    def test_discover_tools_returns_registered_contracts(self):
        adapter = EmailChannelAdapter(tools=(_contract(),))
        self.assertEqual(len(adapter.discover_tools()), 1)


class TestEmailChannelAdapterThroughUniversalToolRegistry(unittest.TestCase):
    def test_real_end_to_end_call_through_tool_runtime(self):
        sent = []
        adapter = EmailChannelAdapter(
            tools=(_contract(),),
            transport=lambda to, subject, body: sent.append((to, subject, body)) or "msg-456",
        )
        registry = UniversalToolRegistry()
        registry.register_adapter(adapter)
        runtime = ToolRuntime(registry, sleep_fn=lambda s: None)

        result = runtime.execute("email", "send-update", {"to": "team@example.com", "subject": "Status", "body": "All green."})

        self.assertEqual(result.status, "success")
        self.assertEqual(len(sent), 1)


if __name__ == "__main__":
    unittest.main()
