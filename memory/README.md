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
_(none yet.)_

## Limitations
Empty as of the initial scaffold (2026-08-06).

## Future improvements
- None planned beyond what's tracked in `memory-factory`'s README.
