"""chunk_text -- splits a document into overlapping word-count chunks.
See CONTRACT.md SS1.
"""

from __future__ import annotations

from typing import Tuple

from .errors import EmptyDocumentError
from .types import Chunk


def chunk_text(document_id: str, text: str, *, chunk_size: int = 500, overlap: int = 50) -> Tuple[Chunk, ...]:
    """Splits `text` into word-count-bounded chunks with `overlap` words
    shared between consecutive chunks (so a fact split across a boundary
    still appears whole in at least one chunk). `chunk_size`/`overlap`
    are in words, not characters, for a stdlib-only, tokenizer-free
    implementation.
    """
    if chunk_size <= overlap:
        raise ValueError(f"chunk_size ({chunk_size}) must be greater than overlap ({overlap})")
    words = text.split()
    if not words:
        raise EmptyDocumentError(f"Document '{document_id}' has no content to chunk")

    chunks = []
    start = 0
    position = 0
    step = chunk_size - overlap
    while start < len(words):
        window = words[start : start + chunk_size]
        chunks.append(
            Chunk(
                document_id=document_id,
                chunk_id=f"{document_id}#{position}",
                text=" ".join(window),
                position=position,
            )
        )
        position += 1
        start += step
    return tuple(chunks)
