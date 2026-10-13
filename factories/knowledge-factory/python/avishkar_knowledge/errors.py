"""Error types for the Knowledge Framework."""

from __future__ import annotations


class KnowledgeFrameworkError(Exception):
    """Base class for every error avishkar_knowledge raises."""


class EmptyDocumentError(KnowledgeFrameworkError):
    """chunk_text() was given empty or whitespace-only text."""


class DimensionMismatchError(KnowledgeFrameworkError):
    """A vector added to a VectorIndex doesn't match its configured
    dimensionality.
    """
