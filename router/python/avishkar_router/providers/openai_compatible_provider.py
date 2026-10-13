"""OpenAICompatibleProvider -- a real ModelProvider for any OpenAI-compatible
Chat Completions endpoint (Groq, OpenRouter, OpenAI, Together, ...). stdlib
`urllib` only, matching RESTAdapter's zero-dependency precedent and keeping the
router's default import path free of any vendor SDK.

One class, three deployments -- the base_url + name + model catalog are
injected, so the same adapter serves Groq today and OpenRouter/OpenAI
tomorrow with no code change:

    OpenAICompatibleProvider(
        api_key=os.environ["GROQ_API_KEY"],
        base_url="https://api.groq.com/openai/v1",
        name="groq",
        models=(ModelSpec("openai/gpt-oss-120b", "groq", ("chat","tools"), ...),),
    )

Errors are normalized into avishkar_router's shared ProviderError hierarchy
(never a raw urllib exception leaves complete()), exactly as the contract
requires of every provider adapter. Not re-exported from providers/__init__
(same policy as AnthropicProvider) -- import it explicitly.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable, Mapping, Optional, Sequence, Tuple

from ..errors import (
    AuthenticationError,
    InvalidRequestError,
    ProviderOverloadedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RateLimitError,
)
from ..provider import ModelProvider
from ..types import CompletionRequest, ModelSpec, ProviderResponse

# transport seam (method already fixed to POST): (url, headers, body) -> (status, bytes)
Transport = Callable[[str, Mapping[str, str], bytes], Tuple[int, bytes]]


def _default_transport(url: str, headers: Mapping[str, str], body: bytes) -> Tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 -- caller-declared endpoint
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


class OpenAICompatibleProvider(ModelProvider):
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str,
        name: str = "openai_compatible",
        models: Sequence[ModelSpec],
        transport: Transport = _default_transport,
        extra_headers: Optional[Mapping[str, str]] = None,
        supports_tools: bool = True,
    ) -> None:
        """`supports_tools=False` silently drops `tools`/`tool_choice` from
        the outgoing payload even when the request carries them -- for a
        host/model known to misbehave when given a tools schema, as
        opposed to a per-request choice. Real, previously-observed case
        (Layla, layla_service.py): DeepSeek via OpenRouter emitted fake
        tool-call attempts as raw text using its own internal special
        tokens instead of real structured tool_calls when given a tools
        schema -- nothing downstream could parse it, and it leaked
        straight through as garbled text. That is a fact about this
        provider instance, not something each caller should have to
        remember to work around."""
        self.name = name
        self._api_key = api_key
        self._base = base_url.rstrip("/")
        self._models = tuple(models)
        self._transport = transport
        self._extra_headers = dict(extra_headers or {})
        self._supports_tools = supports_tools

    def list_models(self) -> Tuple[ModelSpec, ...]:
        return self._models

    def complete(self, request: CompletionRequest, *, model_id: str) -> ProviderResponse:
        messages_payload = []
        for m in request.messages:
            d = {"role": m.role, "content": m.content}
            if m.tool_calls:
                d["tool_calls"] = list(m.tool_calls)
            if m.tool_call_id:
                d["tool_call_id"] = m.tool_call_id
            messages_payload.append(d)

        payload = {
            "model": model_id,
            "messages": messages_payload,
            "max_tokens": request.max_tokens,
        }
        # Phase 1: only when this provider instance actually supports tools
        # (see __init__'s supports_tools docstring) AND the request asked
        # for them -- neither alone is enough.
        if request.tools and self._supports_tools:
            payload["tools"] = list(request.tools)
            if request.tool_choice is not None:
                payload["tool_choice"] = request.tool_choice
        # Optional passthroughs from CompletionRequest.metadata (temperature,
        # reasoning_effort -- Groq's gpt-oss honours the latter).
        for key in ("temperature", "reasoning_effort", "top_p"):
            if key in request.metadata:
                payload[key] = request.metadata[key]

        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            # Some OpenAI-compatible hosts (Groq behind Cloudflare) reject
            # urllib's default "Python-urllib/x.y" UA with a 403/1010 firewall
            # block. Present a normal client UA unless the caller overrides it.
            "User-Agent": "avishkar-router/1.0",
            **self._extra_headers,
        }
        url = f"{self._base}/chat/completions"

        try:
            status, raw = self._transport(url, headers, body)
        except urllib.error.URLError as exc:
            # DNS / connection / timeout at the socket layer.
            if isinstance(getattr(exc, "reason", None), TimeoutError):
                raise ProviderTimeoutError(f"{self.name} request timed out: {exc}") from exc
            raise ProviderUnavailableError(f"{self.name} connection failed: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 -- normalized into router's hierarchy
            raise ProviderUnavailableError(f"{self.name} request failed: {exc}") from exc

        if status != 200:
            detail = raw.decode("utf-8", errors="replace")[:500]
            if status in (401, 403):
                raise AuthenticationError(f"{self.name} {status}: {detail}")
            if status == 429:
                raise RateLimitError(f"{self.name} 429: {detail}")
            if status == 400:
                raise InvalidRequestError(f"{self.name} 400: {detail}")
            if status == 529:
                raise ProviderOverloadedError(f"{self.name} 529: {detail}")
            raise ProviderUnavailableError(f"{self.name} {status}: {detail}")

        try:
            data = json.loads(raw)
            choice = data["choices"][0]
            message = choice["message"]
            content = message.get("content") or ""  # a tool-call-only response can have content=null
            tool_calls = tuple(message.get("tool_calls") or ())
            usage = data.get("usage", {})
        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            raise ProviderUnavailableError(
                f"{self.name} returned an unparseable response: {exc}"
            ) from exc

        return ProviderResponse(
            content=content,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            stop_reason=choice.get("finish_reason"),
            raw=data,
            request_id=data.get("id"),
            tool_calls=tool_calls,
        )
