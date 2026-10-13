"""Error types for the Core Engine Framework.

Every error a Core Engine component raises is a subclass of
AvishkarCoreError so callers can catch "anything Core Engine raised"
without enumerating every specific type. See CONTRACT.md for which
component raises which error and under what condition.
"""

from __future__ import annotations


class AvishkarCoreError(Exception):
    """Base class for every error raised by avishkar_core."""


class ConfigError(AvishkarCoreError):
    """Config loading, parsing, or a required() key was missing.

    Raised by load_config() and Config.require().
    """


class ModuleAlreadyRegisteredError(AvishkarCoreError):
    """A module name was registered twice without replace=True."""


class ModuleNotRegisteredError(AvishkarCoreError):
    """ModuleRegistry.get() was called with an unknown module name."""


class DependencyDirectionError(AvishkarCoreError):
    """A module manifest declared a dependency that violates the
    platform's dependency direction rule (ARCHITECTURE.md SS5).
    """


class InvalidManifestError(AvishkarCoreError):
    """A module manifest failed validation against
    schemas/module-manifest.schema.json.
    """
