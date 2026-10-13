"""avishkar_router -- Python reference implementation of the AI Router Framework.

See ../CONTRACT.md for the language-agnostic contract this package
implements, and ../README.md for the framework's full documentation.

AnthropicProvider is intentionally NOT re-exported here (it needs the
optional `anthropic` package) -- import it explicitly:

    from avishkar_router.providers.anthropic_provider import AnthropicProvider
"""

from .errors import (
    AuthenticationError,
    DuplicateModelError,
    InvalidRequestError,
    NoAvailableProviderError,
    NoMatchingModelError,
    ProviderError,
    ProviderOverloadedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RateLimitError,
    RouterError,
)
from .policy import RoutingPolicy, RoutingRule
from .provider import ModelProvider
from .providers import MockProvider
from .router import CostTracker, Router
from .types import CompletionRequest, CompletionResponse, Message, ModelSpec, ProviderResponse

__version__ = "0.1.0"

__all__ = [
    "CompletionRequest",
    "CompletionResponse",
    "Message",
    "ModelSpec",
    "ProviderResponse",
    "ModelProvider",
    "MockProvider",
    "RoutingPolicy",
    "RoutingRule",
    "Router",
    "CostTracker",
    "ProviderError",
    "AuthenticationError",
    "RateLimitError",
    "InvalidRequestError",
    "ProviderOverloadedError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "RouterError",
    "NoMatchingModelError",
    "NoAvailableProviderError",
    "DuplicateModelError",
    "__version__",
]
