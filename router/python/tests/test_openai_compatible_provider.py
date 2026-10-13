import json
import unittest

from avishkar_router import CompletionRequest, Message, ModelSpec
from avishkar_router.providers.openai_compatible_provider import OpenAICompatibleProvider


def _fake_transport(status, body_dict):
    """Records the request it was called with and always returns the
    configured (status, body) -- lets tests assert on the exact payload
    sent, not just the parsed result."""
    calls = []

    def transport(url, headers, body):
        calls.append({"url": url, "headers": dict(headers), "body": json.loads(body)})
        return status, json.dumps(body_dict).encode("utf-8")

    transport.calls = calls
    return transport


_SPEC = ModelSpec(
    model_id="test-model", provider="test", capabilities=("chat", "tools"),
    input_cost_per_mtok=0.0, output_cost_per_mtok=0.0, max_context_tokens=1000, max_output_tokens=100,
)


class TestOpenAICompatibleProviderToolCalling(unittest.TestCase):
    def test_tools_included_when_request_has_them_and_provider_supports_them(self):
        transport = _fake_transport(200, {"choices": [{"message": {"content": "ok"}}]})
        provider = OpenAICompatibleProvider(
            "key", base_url="https://example.test/v1", models=(_SPEC,), transport=transport, supports_tools=True,
        )
        request = CompletionRequest(
            messages=(Message(role="user", content="hi"),),
            tools=({"type": "function", "function": {"name": "f"}},),
            tool_choice="auto",
        )

        provider.complete(request, model_id="test-model")

        sent = transport.calls[0]["body"]
        self.assertIn("tools", sent)
        self.assertEqual(sent["tool_choice"], "auto")

    def test_tools_dropped_when_provider_does_not_support_them(self):
        """The real bug this exists for: DeepSeek via OpenRouter emits fake
        tool-call attempts as raw text when given a tools schema -- this
        provider instance must never send one, regardless of what the
        request asks for."""
        transport = _fake_transport(200, {"choices": [{"message": {"content": "ok"}}]})
        provider = OpenAICompatibleProvider(
            "key", base_url="https://example.test/v1", models=(_SPEC,), transport=transport, supports_tools=False,
        )
        request = CompletionRequest(
            messages=(Message(role="user", content="hi"),),
            tools=({"type": "function", "function": {"name": "f"}},),
            tool_choice="auto",
        )

        provider.complete(request, model_id="test-model")

        sent = transport.calls[0]["body"]
        self.assertNotIn("tools", sent)
        self.assertNotIn("tool_choice", sent)

    def test_tool_calls_extracted_from_response(self):
        raw_tool_calls = [{"id": "call_1", "type": "function", "function": {"name": "f", "arguments": "{}"}}]
        transport = _fake_transport(200, {"choices": [{"message": {"content": None, "tool_calls": raw_tool_calls}}]})
        provider = OpenAICompatibleProvider(
            "key", base_url="https://example.test/v1", models=(_SPEC,), transport=transport,
        )
        request = CompletionRequest(messages=(Message(role="user", content="hi"),), tools=({"type": "function"},))

        result = provider.complete(request, model_id="test-model")

        self.assertEqual(result.content, "")  # null content on a tool-call-only response -> "", not a crash
        self.assertEqual(list(result.tool_calls), raw_tool_calls)

    def test_assistant_tool_calls_and_tool_role_messages_round_trip_into_payload(self):
        transport = _fake_transport(200, {"choices": [{"message": {"content": "ok"}}]})
        provider = OpenAICompatibleProvider(
            "key", base_url="https://example.test/v1", models=(_SPEC,), transport=transport,
        )
        request = CompletionRequest(messages=(
            Message(role="user", content="what's the weather"),
            Message(role="assistant", content="", tool_calls=({"id": "call_1", "type": "function",
                                                                 "function": {"name": "get_weather", "arguments": "{}"}},)),
            Message(role="tool", content="sunny", tool_call_id="call_1"),
        ))

        provider.complete(request, model_id="test-model")

        sent_messages = transport.calls[0]["body"]["messages"]
        self.assertEqual(sent_messages[1]["tool_calls"][0]["id"], "call_1")
        self.assertEqual(sent_messages[2]["tool_call_id"], "call_1")
        self.assertEqual(sent_messages[2]["role"], "tool")

    def test_no_tools_field_sent_when_request_has_none(self):
        """Byte-identical behavior for every pre-Phase-1 text-only caller."""
        transport = _fake_transport(200, {"choices": [{"message": {"content": "ok"}}]})
        provider = OpenAICompatibleProvider(
            "key", base_url="https://example.test/v1", models=(_SPEC,), transport=transport,
        )
        request = CompletionRequest(messages=(Message(role="user", content="hi"),))

        provider.complete(request, model_id="test-model")

        sent = transport.calls[0]["body"]
        self.assertNotIn("tools", sent)
        self.assertNotIn("tool_choice", sent)


if __name__ == "__main__":
    unittest.main()
