"""Errors for Layla. See CONTRACT.md SS13."""

from __future__ import annotations


class LaylaError(Exception):
    """Base class for every error this package raises."""


class InvalidTransitionError(LaylaError):
    """A LaylaTask state transition isn't in ALLOWED_TRANSITIONS."""


class MemoryPolicyViolationError(LaylaError):
    """A remember() call violates LaylaMemoryPolicy's allowed_kinds or
    never_store_patterns.
    """


class UnknownCapabilityError(LaylaError):
    """A PlanStep names a capability no registered agent's domain matches."""


class DelegationTimeoutError(LaylaError):
    """A delegated call exceeded its PlanStep's timeout_seconds."""


class UnresolvedConflictError(LaylaError):
    """ExecutiveSynthesizer refuses to silently pick a side among
    conflicting results with no resolution strategy given. See
    CONTRACT.md SS6.
    """


class ApprovalExpiredError(LaylaError):
    """An ApprovalRequest was checked or acted on after its expiration."""


class ApprovalDeniedError(LaylaError):
    """An action was attempted after its ApprovalRequest was denied."""


class SessionNotFoundError(LaylaError):
    """SessionManager.load() found no persisted task for the given id."""
