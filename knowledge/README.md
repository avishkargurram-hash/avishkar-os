# knowledge/

## Purpose
The library of shared, platform-level knowledge bases and retrieval
sources — the output of
[`factories/knowledge-factory`](../factories/knowledge-factory/README.md).

## Responsibilities
- One directory per knowledge base (`knowledge/<name>/`): its pipeline
  config, source references, and retrieval interface.
- Hold only knowledge that's genuinely useful across more than one
  product (e.g. shared engineering standards, public domain reference
  material) — see the reuse test in [ARCHITECTURE.md](../ARCHITECTURE.md) §1.

## What does NOT belong here
- Ingestion/pipeline generation logic — that's `knowledge-factory`.
- Product-specific or customer data — that lives in the product's own
  repo/infrastructure, never here.

## Inputs
Output from `knowledge-factory` only.

## Outputs
Retrieval interfaces agents can query for shared context.

## Dependencies
`router/` (embedding model selection), `core/`.

## Examples
The pipeline engine (`chunk_text`, `HashingEmbedder`, `VectorIndex`,
`KnowledgeBase`, `as_tool`) lives inside
[`factories/knowledge-factory/python/avishkar_knowledge/`](../factories/knowledge-factory/python/avishkar_knowledge/)
rather than duplicated here — the same precedent `memory/` set for
backends. As of Phase 14, this shelf holds its first real,
product-facing instance:
[`platform-standards/`](./platform-standards/README.md) — a
`KnowledgeBase` seeded with genuine `STANDARDS.md` excerpts
(engineering principles, security checklist, naming conventions),
importable by any product's agents.

## Limitations
One standalone knowledge base (`platform-standards/`) committed as of
Phase 14. See `knowledge-factory`'s README for `HashingEmbedder`'s
known ranking-quality limitations, which apply to every knowledge base
built on it.

## Future improvements
- Additional shared knowledge bases as real cross-product needs are
  identified — built when needed, not speculatively.
