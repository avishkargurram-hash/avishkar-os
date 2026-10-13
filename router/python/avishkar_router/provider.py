"""ModelProvider -- the adapter interface every provider (Anthropic, a
future OpenAI/Google adapter, the reference MockProvider) implements.

See CONTRACT.md SS2 for the full contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Tuple

from .types import CompletionRequest, ModelSpec, ProviderResponse


class ModelProvider(ABC):
    """A provider adapter. Never talks to the Router directly -- it only
    ever receives a CompletionRequest and an explicit model_id, and
    returns a ProviderResponse or raises a ProviderError subtype
    (see errors.py). Error normalization is mandatory: an adapter must
    translate its vendor SDK's exceptions into the shared ProviderError
    hierarchy before they leave complete().
    """

    #: Stable identifier, e.g. "anthropic". Set by each concrete subclass.
    name: str

    @abstractmethod
    def list_models(self) -> Tuple[ModelSpec, ...]:
        """Every model this provider can serve."""

    @abstractmethod
    def complete(self, request: CompletionRequest, *, model_id: str) -> ProviderResponse:
        """Complete `request` against `model_id`. Raises a ProviderError
        subtype (never the provider's own vendor exception type) on
        failure -- see CONTRACT.md SS2.
        """
