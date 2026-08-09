"""LaylaMemoryPolicy -- a policy layer around a real
avishkar_agent.MemoryPolicy. See CONTRACT.md SS2.

Not a second memory system: every remember()/recall()/forget() call
passes straight through to the wrapped backend. This module adds what
the backend itself has no opinion on -- confidence, provenance,
importance, an allowed-kinds allowlist, and a secret-shaped-value
refusal (reusing security-factory.scan_for_secrets, not a new
detector).
"""

from __future__ import annotations

import datetime
from typing import Any, Optional, Sequence

from avishkar_agent import MemoryPolicy
from avishkar_security import scan_for_secrets

from .errors import MemoryPolicyViolationError
from .types import MEMORY_KINDS, MemoryRecord


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _contains_secret(value: Any) -> bool:
    """Recursively scans string content within value (dict/list/str)
    for secret-shaped patterns. A non-string leaf (int/float/bool/None)
    can't be a secret and is skipped.
    """
    if isinstance(value, str):
        return bool(scan_for_secrets(value))
    if isinstance(value, dict):
        return any(_contains_secret(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_secret(v) for v in value)
    return False


class LaylaMemoryPolicy:
    """Wraps a real MemoryPolicy backend. See CONTRACT.md SS2."""

    def __init__(self, backend: MemoryPolicy, *, allowed_kinds: Sequence[str] = MEMORY_KINDS) -> None:
        self._backend = backend
        self._allowed_kinds = frozenset(allowed_kinds)

    def remember(
        self,
        kind: str,
        key: str,
        value: Any,
        *,
        confidence: float = 1.0,
        provenance: str = "user",
        importance: str = "normal",
    ) -> None:
        if kind not in self._allowed_kinds:
            raise MemoryPolicyViolationError(
                f"kind {kind!r} is not in this policy's allowed_kinds {sorted(self._allowed_kinds)}"
            )
        if _contains_secret(value):
            raise MemoryPolicyViolationError(
                f"refusing to store secret-shaped content under {kind}:{key!r} -- "
                f"no importance level makes storing a credential acceptable"
            )
        record = MemoryRecord(
            value=value, confidence=confidence, provenance=provenance,
            importance=importance, stored_at=_now(),
        )
        self._backend.remember(kind, key, dataclasses_asdict_record(record))

    def recall(self, kind: str, key: str) -> Optional[MemoryRecord]:
        raw = self._backend.recall(kind, key)
        if raw is None:
            return None
        return MemoryRecord(**raw)

    def forget(self, kind: str, key: str) -> None:
        # Deletion is never a policy decision -- always allowed, even
        # for a kind outside allowed_kinds (a user must always be able
        # to remove something previously stored under a since-narrowed
        # policy). See CONTRACT.md SS2.
        self._backend.forget(kind, key)

    def correct(self, kind: str, key: str, new_value: Any, *, reason: str) -> MemoryRecord:
        existing = self.recall(kind, key)
        confidence = existing.confidence if existing else 1.0
        importance = existing.importance if existing else "normal"
        self.remember(
            kind, key, new_value,
            confidence=confidence, provenance=f"correction: {reason}", importance=importance,
        )
        return self.recall(kind, key)


def dataclasses_asdict_record(record: MemoryRecord) -> dict:
    """A small, explicit conversion (not dataclasses.asdict, which would
    recurse into `value` even when it isn't itself a dataclass) so
    MemoryRecord round-trips through a backend that only stores
    JSON-compatible values (SQLiteMemoryPolicy, Phase 5).
    """
    return {
        "value": record.value,
        "confidence": record.confidence,
        "provenance": record.provenance,
        "importance": record.importance,
        "stored_at": record.stored_at,
    }
