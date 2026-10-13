"""AnthropicProvider -- routes completions to the Anthropic Messages API
via the official `anthropic` SDK (never raw HTTP -- see the claude-api
skill's Output Requirement). Requires `pip install anthropic` (or the
`avishkar-router[anthropic]` extra); imported lazily so the rest of
avishkar_router works without it installed unless this provider is
actually constructed.
"""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

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

# Catalog current as of 2026-08 (see the claude-api skill's model table,
# which is the authoritative source this is derived from -- re-check it
# before trusting these numbers far into the future). Sampling parameters
# (temperature/top_p/top_k) are deliberately not forwarded -- see
# README.md Limitations: they 400 on current-generation Claude models,
# and per-model support varies too much for a v1 contract to encode.
_MODEL_SPECS: Tuple[ModelSpec, ...] = (
    ModelSpec(
        model_id="claude-opus-5",
        provider="anthropic",
        capabilities=("chat", "tools", "vision", "thinking"),
        input_cost_per_mtok=5.00,
        output_cost_per_mtok=25.00,
        max_context_tokens=1_000_000,
        max_output_tokens=128_000,
    ),
    ModelSpec(
        model_id="claude-sonnet-5",
        provider="anthropic",
        capabilities=("chat", "tools", "vision", "thinking"),
        input_cost_per_mtok=3.00,
        output_cost_per_mtok=15.00,
        max_context_tokens=1_000_000,
        max_output_tokens=128_000,
    ),
    ModelSpec(
        model_id="claude-haiku-4-5",
        provider="anthropic",
        capabilities=("chat", "tools", "vision"),
        input_cost_per_mtok=1.00,
        output_cost_per_mtok=5.00,
        max_context_tokens=200_000,
        max_output_tokens=64_000,
    ),
)


class AnthropicProvider(ModelProvider):
    """Real, network-calling provider adapter."""

    name = "anthropic"

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        models: Optional[Sequence[ModelSpec]] = None,
        client: Optional[object] = None,
    ) -> None:
        """`client`, if given, is used verbatim instead of constructing a
        real anthropic.Anthropic() -- the seam tests use to inject a fake
        client without needing the real package installed or a network
        call. Production callers never pass it.
        """
        if client is not None:
            self._client = client
        else:
            try:
                import anthropic
            except ImportError as exc:
                raise ImportError(
                    "AnthropicProvider requires the 'anthropic' package. "
                    "Install it with 'pip install anthropic' or the "
                    "'avishkar-router[anthropic]' extra."
                ) from exc
            self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self._models = tuple(models) if models else _MODEL_SPECS

    def list_models(self) -> Tuple[ModelSpec, ...]:
        return self._models

    def complete(self, request: CompletionRequest, *, model_id: str) -> ProviderResponse:
        import anthropic  # already verified importable (or a fake client was injected)

        try:
            response = self._client.messages.create(
                model=model_id,
                max_tokens=request.max_tokens,
                messages=[{"role": m.role, "content": m.content} for m in request.messages],
            )
        # Order matters: most specific first. All of these subclass
        # anthropic.APIStatusError except APIConnectionError, which is a
        # sibling -- see shared/error-codes.md's typed-exception table.
        except anthropic.RateLimitError as exc:
            raise RateLimitError(str(exc)) from exc
        except anthropic.AuthenticationError as exc:
            raise AuthenticationError(str(exc)) from exc
        except anthropic.PermissionDeniedError as exc:
            raise AuthenticationError(str(exc)) from exc
        except anthropic.NotFoundError as exc:
            raise InvalidRequestError(str(exc)) from exc
        except anthropic.BadRequestError as exc:
            raise InvalidRequestError(str(exc)) from exc
        except anthropic.APIConnectionError as exc:
            # APITimeoutError subclasses APIConnectionError in the
            # official SDK, so this branch covers both.
            if isinstance(exc, getattr(anthropic, "APITimeoutError", ())):
                raise ProviderTimeoutError(str(exc)) from exc
            raise ProviderUnavailableError(str(exc)) from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code == 529:
                raise ProviderOverloadedError(str(exc)) from exc
            raise ProviderUnavailableError(str(exc)) from exc

        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        return ProviderResponse(
            content=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason,
            raw=response,
            request_id=getattr(response, "id", None),
        )
