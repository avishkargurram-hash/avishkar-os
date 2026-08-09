"""ProjectStore -- persists generic Project records through
LaylaMemoryPolicy. See CONTRACT.md SS3.

Deliberately generic: no product (Tryvanta, Humanify OS, ...) is named
anywhere in this module. Consistent with starter-kit-factory's
ADR-0016 precedent against hardcoding named products into the platform.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from .memory_policy import LaylaMemoryPolicy
from .types import Project

_KIND = "long_term"
_KEY_PREFIX = "project:"
_INDEX_KEY = "project:__index__"


def _project_to_dict(project: Project) -> dict:
    return dataclasses.asdict(project)


def _project_from_dict(data: dict) -> Project:
    return Project(**data)


class ProjectStore:
    """Persists Projects through the same LaylaMemoryPolicy every other
    Layla component uses -- one storage mechanism, not a second one.
    See CONTRACT.md SS3.
    """

    def __init__(self, memory: LaylaMemoryPolicy) -> None:
        self._memory = memory

    def save(self, project: Project) -> None:
        self._memory.remember(
            _KIND, f"{_KEY_PREFIX}{project.id}", _project_to_dict(project),
            provenance="project-store", importance="high",
        )
        index_record = self._memory.recall(_KIND, _INDEX_KEY)
        ids = set(index_record.value) if index_record else set()
        ids.add(project.id)
        self._memory.remember(_KIND, _INDEX_KEY, sorted(ids), provenance="project-store")

    def load(self, project_id: str) -> Optional[Project]:
        record = self._memory.recall(_KIND, f"{_KEY_PREFIX}{project_id}")
        return _project_from_dict(record.value) if record else None

    def list_ids(self) -> tuple:
        record = self._memory.recall(_KIND, _INDEX_KEY)
        return tuple(record.value) if record else ()

    def list_all(self) -> tuple:
        return tuple(self.load(pid) for pid in self.list_ids())
