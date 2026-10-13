"""Errors for the Security Framework. See CONTRACT.md SS4."""

from __future__ import annotations


class SecurityFrameworkError(Exception):
    """Base class for every error this framework raises."""


class MissingAnswerError(SecurityFrameworkError):
    """run_checklist() was called without an answer for every
    SECURITY_CHECKLIST item.
    """


class UnknownChecklistItemError(SecurityFrameworkError):
    """run_checklist() was given an answer for an id that isn't a real
    checklist item -- almost always a typo.
    """
