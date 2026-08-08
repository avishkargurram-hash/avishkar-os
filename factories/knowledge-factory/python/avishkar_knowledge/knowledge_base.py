"""KnowledgeBase -- ties chunker + embedder + index together into
ingest()/search(). See CONTRACT.md SS1.
"""

from __future__ import annotations

from typing import Optional, Tuple

from avishkar_core import get_logger

from .chunker import chunk_text
from .embedder import Embedder, HashingEmbedder
from .index import VectorIndex
from .types import Chunk, SearchResult


class KnowledgeBase:
    def __init__(
        self,
        embedder: Optional[Embedder] = None,
        index: Optional[VectorIndex] = None,
        *,
        chunk_size: int = 500,
        overlap: int = 50,
        logger=None,
    ) -> None:
        self._embedder = embedder or HashingEmbedder()
        self._index = index or VectorIndex(self._embedder.dimensions)
        self._chunk_size = chunk_size
        self._overlap = overlap
        self._logger = logger or get_logger("knowledge.base")

    def ingest(self, document_id: str, text: str) -> Tuple[Chunk, ...]:
        chunks = chunk_text(document_id, text, chunk_size=self._chunk_size, overlap=self._overlap)
        for chunk in chunks:
            vector = self._embedder.embed(chunk.text)
            self._index.add(chunk, vector)
        self._logger.info("Document ingested", document_id=document_id, chunks=len(chunks))
        return chunks

    def search(self, query: str, *, top_k: int = 5) -> Tuple[SearchResult, ...]:
        query_vector = self._embedder.embed(query)
        results = self._index.search(query_vector, top_k=top_k)
        self._logger.info("Knowledge search", query=query, results=len(results))
        return results

    def __len__(self) -> int:
        return len(self._index)
