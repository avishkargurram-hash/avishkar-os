"""avishkar_knowledge -- Python reference implementation of the
Knowledge Framework: chunk -> embed -> index -> retrieve, stdlib-only.

See ../CONTRACT.md and ../README.md for full documentation.
"""

from .agent_bridge import as_tool
from .chunker import chunk_text
from .embedder import Embedder, HashingEmbedder
from .errors import DimensionMismatchError, EmptyDocumentError, KnowledgeFrameworkError
from .index import VectorIndex
from .knowledge_base import KnowledgeBase
from .types import Chunk, SearchResult

__version__ = "0.1.0"

__all__ = [
    "Chunk",
    "SearchResult",
    "chunk_text",
    "Embedder",
    "HashingEmbedder",
    "VectorIndex",
    "KnowledgeBase",
    "as_tool",
    "KnowledgeFrameworkError",
    "EmptyDocumentError",
    "DimensionMismatchError",
    "__version__",
]
