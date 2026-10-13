"""Errors for the Evaluation Framework. See CONTRACT.md SS6."""

from __future__ import annotations


class EvaluationFrameworkError(Exception):
    """Base class for every error this framework raises."""


class EmptyCaseSetError(EvaluationFrameworkError):
    """An EvalSuite has no cases -- see CONTRACT.md SS2 for why this is
    an error rather than a silent 0.0 score.
    """
