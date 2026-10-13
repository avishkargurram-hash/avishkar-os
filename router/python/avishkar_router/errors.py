"""Error types for the AI Router Framework.

Two hierarchies: ProviderError (what a ModelProvider adapter raises,
normalized across vendors -- see CONTRACT.md SS2) and RouterError (what
the Router itself raises). Keeping them separate lets calling code
distinguish "this specific provider call failed" (often retryable via
fallback -- the Router already does this for you) from "the router
itself couldn't complete the request at all" (candidates exhausted, or a
policy/registration bug).
"""

from __future__ import annotations


class ProviderError(Exception):
    """Base class for every error a ModelProvider.complete() raises.

    A provider adapter MUST translate its underlying SDK/HTTP errors into
    one of these subtypes before they leave complete() -- see CONTRACT.md
    SS2 and README.md Anti-Patterns.
    """


class AuthenticationError(ProviderError):
    """Invalid or missing credentials for the provider."""


class RateLimitError(ProviderError):
    """The provider rejected the request due to rate limiting."""


class InvalidRequestError(ProviderError):
    """The request was malformed, or named an unknown model."""


class ProviderOverloadedError(ProviderError):
    """The provider is temporarily overloaded (e.g. HTTP 529)."""


class ProviderTimeoutError(ProviderError):
    """The provider call exceeded its timeout."""


class ProviderUnavailableError(ProviderError):
    """A connection-level failure reaching the provider."""


class RouterError(Exception):
    """Base class for every error the Router itself raises (as opposed to
    a ProviderError bubbling up from an adapter).
    """


class NoMatchingModelError(RouterError):
    """A candidate model_id from RoutingPolicy isn't registered with any
    provider passed to this Router.
    """


class NoAvailableProviderError(RouterError):
    """Every candidate model for this request failed. Raised only after
    the full fallback chain has been exhausted.
    """


class DuplicateModelError(RouterError):
    """Two providers registered with the same Router publish the same
    model_id -- refused at construction time rather than silently
    picking one (CONTRACT.md SS4).
    """
