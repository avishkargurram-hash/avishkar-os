"""MockProvider -- deterministic, network-free ModelProvider. The default
for tests and for the quickstart example, so both run without an API key.
"""

from __future__ import annotations

from typing import Optional, Sequence, Set, Tuple

from ..errors import ProviderUnavailableError
from ..provider import ModelProvider
from ..types import CompletionRequest, ModelSpec, ProviderResponse

_DEFAULT_MODELS: Tuple[ModelSpec, ...] = (
    ModelSpec(
        model_id="mock-fast",
        provider="mock",
        capabilities=("chat",),
        input_cost_per_mtok=0.0,
        output_cost_per_mtok=0.0,
        max_context_tokens=8_192,
        max_output_tokens=2_048,
    ),
)


class MockProvider(ModelProvider):
    """Returns a fixed response, counting words as a stand-in token
    count. `fail_models` lets a test force this provider to raise for
    specific model_ids, to exercise Router fallback without a second
    real provider.
    """

    name = "mock"

    def __init__(
        self,
        models: Optional[Sequence[ModelSpec]] = None,
        *,
        response_text: str = "This is a mock response.",
        fail_models: Sequence[str] = (),
    ) -> None:
        self._models = tuple(models) if models else _DEFAULT_MODELS
        self._response_text = response_text
        self._fail_models: Set[str] = set(fail_models)

    def list_models(self) -> Tuple[ModelSpec, ...]:
        return self._models

    def complete(self, request: CompletionRequest, *, model_id: str) -> ProviderResponse:
        if model_id in self._fail_models:
            raise ProviderUnavailableError(
                f"MockProvider configured to fail for model '{model_id}'"
            )
        input_tokens = sum(len(m.content.split()) for m in request.messages)
        output_tokens = len(self._response_text.split())
        return ProviderResponse(
            content=self._response_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            stop_reason="end_turn",
        )
