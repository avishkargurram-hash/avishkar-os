"""Errors for the Workflow Framework. See CONTRACT.md SS7."""

from __future__ import annotations


class WorkflowFrameworkError(Exception):
    """Base class for every error this framework raises."""


class DuplicateStepError(WorkflowFrameworkError):
    """Two steps in a WorkflowSpec share the same id."""


class UnknownStepError(WorkflowFrameworkError):
    """A `next`/`start`/branch value names a step id that doesn't exist."""


class StepExecutionError(WorkflowFrameworkError):
    """A step's handler raised after its retry policy was exhausted.

    Chains the original exception via `raise ... from original` so the
    real cause is never hidden.
    """


class MaxStepsExceededError(WorkflowFrameworkError):
    """The engine's cycle guard tripped -- see CONTRACT.md SS4."""
