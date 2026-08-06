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
_(none yet.)_

## Limitations
Empty as of the initial scaffold (2026-08-06).

## Future improvements
- None planned beyond what's tracked in `knowledge-factory`'s README.
