"""AuditLogger. See CONTRACT.md SS9.

Persisted through the same LaylaMemoryPolicy every other Layla
component uses, under kind="episodic" (an audit trail is inherently a
sequence of dated events) with keys namespaced audit:{task_id or
"system"}:{sequence}. Never stores a model's raw chain-of-thought --
only structured fields, per Part XV.
"""

from __future__ import annotations

import dataclasses
import datetime
from typing import Any, Dict, Mapping, Optional, Tuple

from .memory_policy import LaylaMemoryPolicy
from .types import AuditRecord

_KIND = "episodic"


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _scope(task_id: Optional[str]) -> str:
    return task_id or "system"


class AuditLogger:
    def __init__(self, memory: LaylaMemoryPolicy) -> None:
        self._memory = memory

    def record(self, event_type: str, payload: Mapping[str, Any], *, task_id: Optional[str] = None) -> AuditRecord:
        scope = _scope(task_id)
        index_key = f"audit:__index__:{scope}"
        index_record = self._memory.recall(_KIND, index_key)
        sequence = len(index_record.value) if index_record else 0
        entry_key = f"audit:{scope}:{sequence}"

        record = AuditRecord(event_type=event_type, payload=dict(payload), task_id=task_id, recorded_at=_now())
        self._memory.remember(_KIND, entry_key, dataclasses.asdict(record), provenance="audit-logger")

        keys = list(index_record.value) if index_record else []
        keys.append(entry_key)
        self._memory.remember(_KIND, index_key, keys, provenance="audit-logger")

        return record

    def history(self, task_id: Optional[str] = None) -> Tuple[AuditRecord, ...]:
        scope = _scope(task_id)
        index_record = self._memory.recall(_KIND, f"audit:__index__:{scope}")
        if index_record is None:
            return ()
        records = []
        for key in index_record.value:
            entry = self._memory.recall(_KIND, key)
            if entry is not None:
                records.append(AuditRecord(**entry.value))
        return tuple(records)
