"""Errors for the robotics safety layer. See CONTRACT.md SS44."""

from __future__ import annotations

from ..errors import LaylaError


class RobotEmergencyStoppedError(LaylaError):
    """An action was requested while the emergency-stop latch is set.
    Only an explicit `reset_emergency_stop()` call clears this -- never
    automatically, never as a side effect of a normal action request.
    """


class RobotActionTimeoutError(LaylaError):
    """A real driver call did not return within the configured
    action_timeout_seconds. Triggers a real fail-safe callback and
    latches the emergency stop before this is raised.
    """


class RobotActionFailedError(LaylaError):
    """A real driver call raised an exception. Triggers a real
    fail-safe callback and latches the emergency stop before this is
    raised.
    """
