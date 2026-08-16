import unittest

from avishkar_integration import ProtocolInvocationError, RateLimit, RetryPolicy, ToolContract, ToolExecutionRequest, ToolRuntime, UniversalToolRegistry

from avishkar_layla.channels.email_adapter import EmailChannelAdapter
from avishkar_layla.channels.whatsapp_adapter import WhatsAppChannelAdapter


def _contract() -> ToolContract:
    return ToolContract(
        identity="send-message",
        description="Send a routine WhatsApp status update.",
        protocol="whatsapp",
        input_schema={"type": "object", "required": ["to", "body"]},
        rate_limit=RateLimit(requests_per_minute=30),
        retry_policy=RetryPolicy(max_attempts=1),
    )


class TestWhatsAppChannelAdapterUnconfigured(unittest.TestCase):
    def test_unconfigured_transport_raises_the_documented_boundary_error(self):
        adapter = WhatsAppChannelAdapter(tools=(_contract(),))
        request = ToolExecutionRequest(input={"to": "+15550001111", "body": "Update."})
        with self.assertRaises(ProtocolInvocationError) as ctx:
            adapter.invoke(_contract(), request)
        self.assertIn("ADAPTER READY", str(ctx.exception))


class TestWhatsAppChannelAdapterWithFakeTransport(unittest.TestCase):
    def test_successful_send_returns_message_id(self):
        sent = []

        def fake_transport(to, body):
            sent.append((to, body))
            return "wamid-123"

        adapter = WhatsAppChannelAdapter(tools=(_contract(),), transport=fake_transport)
        request = ToolExecutionRequest(input={"to": "+15550001111", "body": "Update."})

        result = adapter.invoke(_contract(), request)

        self.assertEqual(result.status, "success")
        self.assertEqual(result.output["message_id"], "wamid-123")
        self.assertEqual(sent, [("+15550001111", "Update.")])

    def test_missing_to_field_raises(self):
        adapter = WhatsAppChannelAdapter(tools=(_contract(),), transport=lambda to, b: "x")
        request = ToolExecutionRequest(input={"body": "Update."})
        with self.assertRaises(ProtocolInvocationError):
            adapter.invoke(_contract(), request)

    def test_transport_failure_is_normalized_into_protocol_invocation_error(self):
        def failing_transport(to, body):
            raise RuntimeError("WhatsApp API unavailable")

        adapter = WhatsAppChannelAdapter(tools=(_contract(),), transport=failing_transport)
        request = ToolExecutionRequest(input={"to": "+15550001111", "body": "x"})

        with self.assertRaises(ProtocolInvocationError):
            adapter.invoke(_contract(), request)

    def test_discover_tools_returns_registered_contracts(self):
        adapter = WhatsAppChannelAdapter(tools=(_contract(),))
        self.assertEqual(len(adapter.discover_tools()), 1)


class TestMultiChannelRoutingThroughOneRegistry(unittest.TestCase):
    """Mission Layla Part 9: routing across channels is already
    UniversalToolRegistry's job (Phase 4, locked) -- one registry, two
    adapters, no second router built for this mission.
    """

    def test_email_and_whatsapp_adapters_coexist_in_one_registry(self):
        email_sent, whatsapp_sent = [], []
        email_adapter = EmailChannelAdapter(
            tools=(ToolContract(
                identity="send-update", description="d", protocol="email",
                input_schema={"type": "object"}, rate_limit=RateLimit(requests_per_minute=30),
                retry_policy=RetryPolicy(max_attempts=1),
            ),),
            transport=lambda to, subject, body: email_sent.append((to, subject, body)) or "email-1",
        )
        whatsapp_adapter = WhatsAppChannelAdapter(
            tools=(_contract(),),
            transport=lambda to, body: whatsapp_sent.append((to, body)) or "wa-1",
        )
        registry = UniversalToolRegistry()
        registry.register_adapter(email_adapter)
        registry.register_adapter(whatsapp_adapter)
        runtime = ToolRuntime(registry, sleep_fn=lambda s: None)

        email_result = runtime.execute("email", "send-update", {"to": "a@example.com", "subject": "s", "body": "b"})
        whatsapp_result = runtime.execute("whatsapp", "send-message", {"to": "+15550001111", "body": "hi"})

        self.assertEqual(email_result.status, "success")
        self.assertEqual(whatsapp_result.status, "success")
        self.assertEqual(len(email_sent), 1)
        self.assertEqual(len(whatsapp_sent), 1)


if __name__ == "__main__":
    unittest.main()
