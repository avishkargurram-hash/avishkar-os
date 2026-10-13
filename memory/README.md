# memory/

## Purpose
The library of shared memory backend implementations and schemas
(short-term, long-term, episodic) — the output of
[`factories/memory-factory`](../factories/memory-factory/README.md).

## Responsibilities
- One directory per memory backend (`memory/<name>/`): its storage
  adapter and the schema/interface it implements.
- Provide the storage-agnostic interface (`get`/`put`/`search`/`forget`)
  agents and graphs code against, so the underlying store can change
  without callers changing.

## What does NOT belong here
- Backend-generation logic — that's `memory-factory`.
- A product's specific memory *content* or schema of what facts matter to
  it — that's product logic, configured on top of a backend from here.
- Actual runtime memory data (databases, indexes) — never committed; see
  `.gitignore`.

## Inputs
Output from `memory-factory` only.

## Outputs
Memory backend adapters agents/graphs can be configured to use.

## Dependencies
`core/`, optionally `knowledge/`.

## Examples
As of Phase 5, the two real backends (`FileMemoryPolicy`,
`SQLiteMemoryPolicy`) live inside
[`factories/memory-factory/python/avishkar_memory/backends/`](../factories/memory-factory/python/avishkar_memory/backends/)
rather than a separate `memory/<name>/` copy — the same precedent
`router/` set for provider adapters and `mcp/` for protocol adapters:
when a factory's own package *is* the reusable shelf, this directory
stays the conceptual home (referenced from every other README) without
a redundant physical duplicate.

## Limitations
No standalone artifacts committed directly under `memory/` yet — see
Examples for where the real, working backends actually live.

## Future improvements
- If a memory backend ever needs product-facing files distinct from
  `memory-factory`'s own package (e.g. a hosted config), it lands here;
  not needed for the two backends that exist today.
