"""Errors for Layla. See CONTRACT.md SS15."""

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


class UnauthenticatedError(LaylaError):
    """No valid, unexpired, unrevoked Session for a given session_id."""


class PermissionDeniedError(LaylaError):
    """An authenticated Session lacks a required permission or capability."""


class EscalationDeniedError(LaylaError):
    """An 'agent' kind Principal was about to be granted a permission it
    can never hold (PERM_INVOKE_AGENT_HIGH_RISK, PERM_APPROVE) -- the
    structural anti-self-escalation guard. See identity.py.
    """


class IdempotencyConflictError(LaylaError):
    """An ExecutionRecord's idempotency key was reused with different
    parameters than its original request -- see execution.py.
    """


class UnknownExecutionOutcomeError(LaylaError):
    """A side-effecting operation's outcome could not be determined (e.g.
    a timeout after the provider may have already acted) -- see
    execution.py SS2's UNKNOWN state.
    """
