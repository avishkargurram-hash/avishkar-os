"""Errors for the Prompt Framework. See CONTRACT.md SS6."""

from __future__ import annotations


class PromptFrameworkError(Exception):
    """Base class for every error this framework raises."""


class UnknownVariableError(PromptFrameworkError):
    """A template references `{name}` that isn't a declared PromptVariable."""


class MissingVariableError(PromptFrameworkError):
    """A required PromptVariable wasn't supplied at render time."""


class DuplicateVersionError(PromptFrameworkError):
    """A (name, version) pair was already registered -- versions are
    immutable once registered, see CONTRACT.md SS3.
    """


class UnknownVersionError(PromptFrameworkError):
    """A named prompt or a specific version of it doesn't exist in the
    registry.
    """
