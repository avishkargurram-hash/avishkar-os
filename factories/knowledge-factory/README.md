# Knowledge Framework

## Vision
A Chief Domain Agent's "Domain Knowledge Architecture" and "Knowledge
Sources" (agent template §3, §11) need somewhere real to point at.
Knowledge Framework is the ingest → chunk → embed → index → retrieve
pipeline behind that — stdlib-only, offline-capable, real cosine-
similarity search today, with an honest, documented path to real
embedding models once AI Router exposes one.

## Architecture
```
factories/knowledge-factory/python/avishkar_knowledge/
├── chunker.py         chunk_text() -- overlapping word-count chunks
├── embedder.py         Embedder ABC + HashingEmbedder (feature hashing, stdlib-only)
├── index.py            VectorIndex -- cosine-similarity search
├── knowledge_base.py    KnowledgeBase -- ingest()/search(), ties the above together
└── agent_bridge.py      as_tool(kb) -> avishkar_agent.Tool
```

## Interfaces
`chunk_text(document_id, text, *, chunk_size=500, overlap=50) -> Chunk[]`.
`HashingEmbedder(dimensions=256).embed(text) -> Vector`.
`VectorIndex(dimensions).add(chunk, vector)` / `.search(query_vector, top_k)`.
`KnowledgeBase(embedder=, index=).ingest(document_id, text)` / `.search(query, top_k=5)`.
`as_tool(kb, name="search_knowledge") -> Tool`. Full contract: [CONTRACT.md](./CONTRACT.md).

## Folder Structure / Naming Standards
See tree above; [STANDARDS.md](../../STANDARDS.md) §3.

## Extension Model
A new `Embedder` (e.g. one calling a real embedding API through AI
Router once one exists) or `VectorIndex` (e.g. a persistent/ANN index)
only needs to satisfy the existing interface — `KnowledgeBase` never
changes.

## Examples
`python factories/knowledge-factory/examples/quickstart.py` — ingest two
documents, search, and wrap the result as a real `Tool` an agent
registers and calls.

## Best Practices
- Keep `chunk_size` proportional to how much context a single retrieved
  chunk needs to be useful standalone — too small loses context, too
  large defeats retrieval precision.
- Use distinctive query vocabulary with `HashingEmbedder` — see
  Limitations; it's a real but crude bag-of-words baseline, not a
  semantic model.

## Anti-Patterns
- Treating `HashingEmbedder`'s similarity scores as calibrated
  probabilities — they're relative rankings within one query, not
  comparable across queries or to a "confidence" threshold.
- Building a second bespoke retrieval pipeline inside a Chief Domain
  Agent's domain module instead of using `KnowledgeBase` — the whole
  point of `as_tool()` is one reusable integration point.

## Testing Strategy
20 tests: chunker boundary/overlap behavior, embedder determinism/
normalization/relative-similarity ordering, index dimension checks and
top-k ranking, `KnowledgeBase` end-to-end ingest+search, and the agent
bridge.

## Limitations
- **`HashingEmbedder` is a real but crude technique** — feature hashing
  with raw term counts, no stopword removal, no TF-IDF/IDF weighting. On
  short or generic queries dominated by common words, it can rank the
  wrong document first (observed and documented in
  `examples/quickstart.py`'s original query, kept as guidance rather
  than hidden). Use distinctive query vocabulary; treat this as a
  working baseline, not production-grade semantic search.
- **No persistent index** — `VectorIndex` is in-memory only; combine
  with `memory-factory`'s `FileMemoryPolicy`/`SQLiteMemoryPolicy` (Phase
  5) if durability is needed, or wait for a future persistent index.
- **AI Router has no embeddings endpoint yet** — real neural embeddings
  are a Future Roadmap item gated on that, not on this framework.

## Future Roadmap
- A `RouterEmbedder` once AI Router exposes an embeddings endpoint.
- A persistent `VectorIndex` (SQLite-backed, reusing `memory-factory`'s
  discipline).
- TF-IDF weighting for `HashingEmbedder` as a cheap, still-offline
  quality improvement short of a real embedding model.
