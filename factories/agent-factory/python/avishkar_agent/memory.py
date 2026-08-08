"""MemoryPolicy -- short-term, long-term, episodic, and semantic memory.
See CONTRACT.md SS3 and SS8 of the agent template.

v1 ships one reference implementation, InMemoryMemoryPolicy: process-
local, non-persistent. Real backends arrive from memory-factory
(ROADMAP.md Phase 5) -- this interface is the seam that lets a
persistent backend swap in later without touching ChiefDomainAgent.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

_KINDS = ("short_term", "long_term", "episodic", "semantic")


class MemoryPolicy(ABC):
    """The interface every memory backend implements -- in-process today,
    a real store (vector DB, key-value store, ...) once memory-factory
    ships.
    """

    @abstractmethod
    def remember(self, kind: str, key: str, value: Any) -> None: ...

    @abstractmethod
    def recall(self, kind: str, key: str) -> Optional[Any]: ...

    @abstractmethod
    def forget(self, kind: str, key: str) -> None: ...


class InMemoryMemoryPolicy(MemoryPolicy):
    """Reference implementation: four separate dicts, one per memory
    kind, held for the lifetime of this object. Not persisted, not
    shared across processes -- see README.md Limitations.
    """

    def __init__(self) -> None:
        self._stores: Dict[str, Dict[str, Any]] = {kind: {} for kind in _KINDS}

    def _validate_kind(self, kind: str) -> Dict[str, Any]:
        store = self._stores.get(kind)
        if store is None:
            raise ValueError(f"Unknown memory kind '{kind}' -- expected one of {_KINDS}")
        return store

    def remember(self, kind: str, key: str, value: Any) -> None:
        self._validate_kind(kind)[key] = value

    def recall(self, kind: str, key: str) -> Optional[Any]:
        return self._validate_kind(kind).get(key)

    def forget(self, kind: str, key: str) -> None:
        self._validate_kind(kind).pop(key, None)
