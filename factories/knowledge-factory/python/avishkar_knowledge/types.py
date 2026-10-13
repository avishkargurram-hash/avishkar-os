"""Core data types for the Knowledge Framework. See CONTRACT.md SS1."""

from __future__ import annotations

import dataclasses
from typing import Tuple


@dataclasses.dataclass(frozen=True)
class Chunk:
    document_id: str
    chunk_id: str
    text: str
    position: int


@dataclasses.dataclass(frozen=True)
class SearchResult:
    chunk: Chunk
    score: float


Vector = Tuple[float, ...]
