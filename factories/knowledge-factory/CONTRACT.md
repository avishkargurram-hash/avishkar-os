# Knowledge Framework — Language-Agnostic Contract

Mirrors sibling CONTRACT.md files. Python ships first
([`python/avishkar_knowledge/`](./python/avishkar_knowledge/)).

## 1. Pipeline: ingest → chunk → embed → index → retrieve

```
Chunk { document_id: string, chunk_id: string, text: string, position: int }

chunk_text(document_id: string, text: string, *, chunk_size: int = 500, overlap: int = 50) -> Chunk[]

Embedder {
  dimensions: int
  embed(text: string) -> number[]     # length == dimensions, L2-normalized
}

SearchResult { chunk: Chunk, score: number }   # score = cosine similarity, [-1, 1]

VectorIndex {
  add(chunk: Chunk, vector: number[]) -> void
  search(query_vector: number[], top_k: int) -> SearchResult[]
}

KnowledgeBase(embedder: Embedder, index: VectorIndex | null = null) -> KnowledgeBase
KnowledgeBase.ingest(document_id: string, text: string) -> Chunk[]   # chunks + embeds + indexes
KnowledgeBase.search(query: string, *, top_k: int = 5) -> SearchResult[]
```

**Embedding, stated honestly:** v1 ships `HashingEmbedder` — a
deterministic, offline, stdlib-only feature-hashing embedder (real
cosine-similarity search, not a fake stub), not a state-of-the-art
neural embedding model. AI Router (Phase 2) has no embeddings endpoint
yet — see README.md Limitations/Future Roadmap for the upgrade path
once one exists.

## 2. Agent Integration

```
as_tool(kb: KnowledgeBase, *, name: string = "search_knowledge") -> avishkar_agent.Tool
  # Wraps kb.search() as a Tool a ChiefDomainAgent's ToolRegistry can
  # register directly -- the agent template's "Knowledge Sources" (SS11)
  # section names which KnowledgeBase(s) an agent is wired to; this is
  # how that wiring becomes callable.
```

## Cross-cutting rules
- Depends on Core Engine (`Logger`) and Agent Framework (`Tool`) only.
- Zero third-party dependencies — pure stdlib (`hashlib`/`zlib`, `math`,
  `json`), consistent with Core Engine's own discipline.
- A new `Embedder` or `VectorIndex` implementation never changes
  `KnowledgeBase`'s public interface.
