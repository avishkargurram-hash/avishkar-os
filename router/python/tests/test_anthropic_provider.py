"""Tests for AnthropicProvider.

Uses the `client=` injection seam (see providers/anthropic_provider.py)
with a fake client object, so these tests exercise the real error-
normalization logic against the *real* `anthropic` exception classes
(constructed directly, not over the network) without making any network
call and without depending on network access being available at all.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import httpx

from avishkar_router import CompletionRequest, Message
from avishkar_router.errors import (
    AuthenticationError,
    InvalidRequestError,
    ProviderOverloadedError,
    ProviderUnavailableError,
    RateLimitError,
)
from avishkar_router.providers.anthropic_provider import AnthropicProvider


def _fake_httpx_response(status_code: int) -> httpx.Response:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return httpx.Response(status_code=status_code, request=request)


class _FakeMessages:
    def __init__(self) -> None:
        self.create = MagicMock()


class _FakeAnthropicClient:
    def __init__(self) -> None:
        self.messages = _FakeMessages()


def _fake_success_response(text="hello", input_tokens=10, output_tokens=5, stop_reason="end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
        stop_reason=stop_reason,
    )


def _req() -> CompletionRequest:
    return CompletionRequest(messages=(Message(role="user", content="hi"),))


class TestAnthropicProviderModelCatalog(unittest.TestCase):
    def test_list_models_includes_known_models(self):
        provider = AnthropicProvider(client=_FakeAnthropicClient())
        model_ids = {m.model_id for m in provider.list_models()}
        self.assertIn("claude-opus-5", model_ids)
        self.assertIn("claude-sonnet-5", model_ids)
        self.assertIn("claude-haiku-4-5", model_ids)

    def test_every_model_reports_provider_name_anthropic(self):
        provider = AnthropicProvider(client=_FakeAnthropicClient())
        for spec in provider.list_models():
            self.assertEqual(spec.provider, "anthropic")


class TestAnthropicProviderSuccess(unittest.TestCase):
    def test_complete_returns_provider_response(self):
        client = _FakeAnthropicClient()
        client.messages.create.return_value = _fake_success_response(
            text="hi there", input_tokens=12, output_tokens=3
        )
        provider = AnthropicProvider(client=client)

        result = provider.complete(_req(), model_id="claude-opus-5")

        self.assertEqual(result.content, "hi there")
        self.assertEqual(result.input_tokens, 12)
        self.assertEqual(result.output_tokens, 3)
        self.assertEqual(result.stop_reason, "end_turn")
        client.messages.create.assert_called_once_with(
            model="claude-opus-5",
            max_tokens=1024,
            messages=[{"role": "user", "content": "hi"}],
        )

    def test_ignores_non_text_content_blocks(self):
        client = _FakeAnthropicClient()
        client.messages.create.return_value = SimpleNamespace(
            content=[
                SimpleNamespace(type="thinking", thinking="..."),
                SimpleNamespace(type="text", text="final answer"),
            ],
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            stop_reason="end_turn",
        )
        provider = AnthropicProvider(client=client)

        result = provider.complete(_req(), model_id="claude-opus-5")

        self.assertEqual(result.content, "final answer")

    def test_max_tokens_forwarded_from_request(self):
        client = _FakeAnthropicClient()
        client.messages.create.return_value = _fake_success_response()
        provider = AnthropicProvider(client=client)
        request = CompletionRequest(messages=(Message(role="user", content="hi"),), max_tokens=4096)

        provider.complete(request, model_id="claude-opus-5")

        _, kwargs = client.messages.create.call_args
        self.assertEqual(kwargs["max_tokens"], 4096)


class TestAnthropicProviderErrorNormalization(unittest.TestCase):
    def test_rate_limit_error_normalized(self):
        client = _FakeAnthropicClient()
        client.messages.create.side_effect = anthropic.RateLimitError(
            "rate limited", response=_fake_httpx_response(429), body=None
        )
        provider = AnthropicProvider(client=client)

        with self.assertRaises(RateLimitError):
            provider.complete(_req(), model_id="claude-opus-5")

    def test_authentication_error_normalized(self):
        client = _FakeAnthropicClient()
        client.messages.create.side_effect = anthropic.AuthenticationError(
            "bad key", response=_fake_httpx_response(401), body=None
        )
        provider = AnthropicProvider(client=client)

        with self.assertRaises(AuthenticationError):
            provider.complete(_req(), model_id="claude-opus-5")

    def test_permission_denied_error_normalized_as_authentication(self):
        client = _FakeAnthropicClient()
        client.messages.create.side_effect = anthropic.PermissionDeniedError(
            "forbidden", response=_fake_httpx_response(403), body=None
        )
        provider = AnthropicProvider(client=client)

        with self.assertRaises(AuthenticationError):
            provider.complete(_req(), model_id="claude-opus-5")

    def test_bad_request_error_normalized(self):
        client = _FakeAnthropicClient()
        client.messages.create.side_effect = anthropic.BadRequestError(
            "bad request", response=_fake_httpx_response(400), body=None
        )
        provider = AnthropicProvider(client=client)

        with self.assertRaises(InvalidRequestError):
            provider.complete(_req(), model_id="claude-opus-5")

    def test_not_found_error_normalized_as_invalid_request(self):
        client = _FakeAnthropicClient()
        client.messages.create.side_effect = anthropic.NotFoundError(
            "no such model", response=_fake_httpx_response(404), body=None
        )
        provider = AnthropicProvider(client=client)

        with self.assertRaises(InvalidRequestError):
            provider.complete(_req(), model_id="claude-opus-5")

    def test_overloaded_status_normalized(self):
        client = _FakeAnthropicClient()
        client.messages.create.side_effect = anthropic.APIStatusError(
            "overloaded", response=_fake_httpx_response(529), body=None
        )
        provider = AnthropicProvider(client=client)

        with self.assertRaises(ProviderOverloadedError):
            provider.complete(_req(), model_id="claude-opus-5")

    def test_other_status_error_normalized_as_unavailable(self):
        client = _FakeAnthropicClient()
        client.messages.create.side_effect = anthropic.APIStatusError(
            "server error", response=_fake_httpx_response(500), body=None
        )
        provider = AnthropicProvider(client=client)

        with self.assertRaises(ProviderUnavailableError):
            provider.complete(_req(), model_id="claude-opus-5")

    def test_connection_error_normalized(self):
        client = _FakeAnthropicClient()
        client.messages.create.side_effect = anthropic.APIConnectionError(
            request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        )
        provider = AnthropicProvider(client=client)

        with self.assertRaises(ProviderUnavailableError):
            provider.complete(_req(), model_id="claude-opus-5")


if __name__ == "__main__":
    unittest.main()
