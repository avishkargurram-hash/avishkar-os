"""VectorIndex -- in-memory cosine-similarity search. See CONTRACT.md SS1."""

from __future__ import annotations

import math
from typing import List, Tuple

from .errors import DimensionMismatchError
from .types import Chunk, SearchResult, Vector


def _cosine_similarity(a: Vector, b: Vector) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class VectorIndex:
    def __init__(self, dimensions: int) -> None:
        self._dimensions = dimensions
        self._entries: List[Tuple[Chunk, Vector]] = []

    def add(self, chunk: Chunk, vector: Vector) -> None:
        if len(vector) != self._dimensions:
            raise DimensionMismatchError(
                f"Vector has {len(vector)} dimensions, index expects {self._dimensions}"
            )
        self._entries.append((chunk, vector))

    def search(self, query_vector: Vector, top_k: int = 5) -> Tuple[SearchResult, ...]:
        scored = [
            SearchResult(chunk=chunk, score=_cosine_similarity(query_vector, vector))
            for chunk, vector in self._entries
        ]
        scored.sort(key=lambda r: r.score, reverse=True)
        return tuple(scored[:top_k])

    def __len__(self) -> int:
        return len(self._entries)
