"""Errors for the Template Framework. See CONTRACT.md SS6."""

from __future__ import annotations


class TemplateFrameworkError(Exception):
    """Base class for every error this framework raises."""


class DuplicateFileError(TemplateFrameworkError):
    """Two TemplateFiles in a Template share the same relative_path."""


class DuplicateVersionError(TemplateFrameworkError):
    """A (name, version) pair was already registered."""


class UnknownVersionError(TemplateFrameworkError):
    """A named template or a specific version of it doesn't exist."""


class TemplateInstantiationError(TemplateFrameworkError):
    """instantiate() would overwrite an existing file without
    overwrite=True. See CONTRACT.md SS4.
    """
