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
As of Phase 6, the real pipeline (`chunk_text`, `HashingEmbedder`,
`VectorIndex`, `KnowledgeBase`, `as_tool`) lives inside
[`factories/knowledge-factory/python/avishkar_knowledge/`](../factories/knowledge-factory/python/avishkar_knowledge/)
rather than a separate `knowledge/<name>/` copy — the same precedent
`memory/` set for backends: when a factory's own package *is* the
reusable shelf, this directory stays the conceptual home (referenced
from every other README) without a redundant physical duplicate. A
product-specific knowledge base built with `KnowledgeBase` would land
under `knowledge/<name>/` once one exists.

## Limitations
No standalone knowledge bases committed directly under `knowledge/`
yet — see Examples for where the real, working pipeline lives, and
`knowledge-factory`'s README for `HashingEmbedder`'s known ranking-
quality limitations.

## Future improvements
- None planned beyond what's tracked in `knowledge-factory`'s README.
