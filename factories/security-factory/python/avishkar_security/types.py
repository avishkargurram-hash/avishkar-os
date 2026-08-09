"""Core data types for the Security Framework. See CONTRACT.md SS1-2."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Tuple


@dataclasses.dataclass(frozen=True)
class SecretMatch:
    """One detected secret-shaped match. `preview` is a redacted
    excerpt -- never the full matched text. See CONTRACT.md SS1.
    """

    pattern_name: str
    start: int
    end: int
    preview: str


@dataclasses.dataclass(frozen=True)
class RepositoryFinding:
    """One SecretMatch located in one real file. See CONTRACT.md SS1."""

    path: Path
    match: SecretMatch


@dataclasses.dataclass(frozen=True)
class ChecklistItem:
    """One item in SECURITY_CHECKLIST. See CONTRACT.md SS2."""

    id: str
    question: str
    why: str


@dataclasses.dataclass(frozen=True)
class ChecklistResult:
    item_id: str
    passed: bool
    note: str = ""


@dataclasses.dataclass(frozen=True)
class ReviewReport:
    """Returned by run_checklist(). See CONTRACT.md SS2."""

    subject: str
    results: Tuple[ChecklistResult, ...]

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def failing(self) -> Tuple[ChecklistResult, ...]:
        return tuple(r for r in self.results if not r.passed)
