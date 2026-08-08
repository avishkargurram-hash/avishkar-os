"""Error types for the Memory Framework."""

from __future__ import annotations


class MemoryFrameworkError(Exception):
    """Base class for every error avishkar_memory raises."""


class UnknownBackendError(MemoryFrameworkError):
    """build_memory_policy() was given a MemoryPolicyConfig.backend value
    no known backend implements.
    """


class InvalidMemoryKindError(MemoryFrameworkError):
    """A backend was asked to operate on a kind outside
    {short_term, long_term, episodic, semantic}.
    """
