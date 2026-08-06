# Memory Factory

## Purpose
Generates memory backend schemas and adapters (short-term, long-term,
episodic) — the tooling behind shared memory backends landing in
[`memory/`](../../memory/README.md).

## Responsibilities
- Define memory schema types (conversation buffer, long-term fact store,
  episodic/event log) and the adapter interface agents use to read/write
  them, independent of the underlying storage engine.
- Scaffold a new memory backend implementation (e.g. a specific vector
  store or DB adapter) conforming to that interface.
- Guarantee products configure a memory backend, not fork one — a
  product-specific memory *schema* (what facts matter to that product) is
  product logic and lives in the product repo; the backend and interface
  are what's shared.

## Architecture
_(To be designed in Phase 2.)_ Expected shape: a storage-agnostic memory
interface (`get`, `put`, `search`, `forget`) with pluggable backend
adapters, consumed by `agent-factory`-generated agents and
`langgraph-factory`-generated graphs.

## Inputs
A memory backend spec: type (short/long/episodic), storage engine,
retention policy.

## Outputs
A memory backend adapter package in `memory/<name>/`.

## Dependencies
`core/`, optionally `knowledge-factory` output if memory retrieval is
knowledge-base-backed.

## Examples
_(none yet.)_

## Limitations
Not implemented yet.

## Future improvements
- Retention/forgetting policies enforced automatically (PII expiry,
  episodic decay) rather than left to each product to implement.
