"""Errors for the Starter Kit Framework. See CONTRACT.md SS5."""

from __future__ import annotations


class StarterKitFrameworkError(Exception):
    """Base class for every error this framework raises."""


class DuplicateVersionError(StarterKitFrameworkError):
    """A (name, version) pair was already registered."""


class UnknownVersionError(StarterKitFrameworkError):
    """A named starter kit or a specific version of it doesn't exist."""
