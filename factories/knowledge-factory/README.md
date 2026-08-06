# Knowledge Factory

## Purpose
Generates knowledge base and retrieval pipeline scaffolds (ingestion,
chunking, embedding, indexing, retrieval config) — the tooling behind
shared knowledge bases landing in [`knowledge/`](../../knowledge/README.md).

## Responsibilities
- Define the knowledge base spec: source(s), ingestion/refresh cadence,
  embedding model, chunking strategy, retrieval config.
- Scaffold a new knowledge base pipeline wired to `router/` for embedding
  model selection and to `memory/` if retrieval results feed back into
  agent memory.
- Keep knowledge bases here **platform-shared, not product-specific data**
  — a product's private customer data pipeline belongs in that product's
  repo, not here (see ARCHITECTURE.md §1's reuse test).

## Architecture
_(To be designed in Phase 2.)_ Expected shape: pipeline config
(source → chunker → embedder → index) plus a retrieval interface agents
call through, so the underlying vector store/index can change without
agents changing.

## Inputs
A knowledge base spec: sources, refresh policy, embedding/chunking config.

## Outputs
A knowledge base pipeline package in `knowledge/<name>/`.

## Dependencies
`router/` (embedding model selection), `core/`.

## Examples
_(none yet.)_

## Limitations
Not implemented yet.

## Future improvements
- Automatic staleness detection/refresh scheduling for source-backed
  knowledge bases.
