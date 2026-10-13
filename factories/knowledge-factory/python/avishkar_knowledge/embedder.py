"""Embedder -- text-to-vector. See CONTRACT.md SS1.

HashingEmbedder is a real, deterministic, offline embedding technique
(the "hashing trick" / feature hashing): each token is hashed into one
of `dimensions` buckets via a stable hash (zlib.crc32 -- NOT Python's
built-in hash(), which is randomized per-process for strings), bucket
counts form the raw vector, then it's L2-normalized so cosine similarity
is well-defined. It is a real, legitimate baseline -- not a neural
embedding model. See README.md Limitations for the honest comparison and
the upgrade path once AI Router exposes an embeddings endpoint.
"""

from __future__ import annotations

import math
import re
import zlib
from abc import ABC, abstractmethod
from typing import Tuple

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> Tuple[str, ...]:
    return tuple(_TOKEN_PATTERN.findall(text.lower()))


class Embedder(ABC):
    dimensions: int

    @abstractmethod
    def embed(self, text: str) -> Tuple[float, ...]: ...


class HashingEmbedder(Embedder):
    def __init__(self, dimensions: int = 256) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> Tuple[float, ...]:
        buckets = [0.0] * self.dimensions
        for token in _tokenize(text):
            index = zlib.crc32(token.encode("utf-8")) % self.dimensions
            buckets[index] += 1.0
        norm = math.sqrt(sum(v * v for v in buckets))
        if norm == 0.0:
            return tuple(buckets)  # all-zero vector for empty/no-token text
        return tuple(v / norm for v in buckets)
