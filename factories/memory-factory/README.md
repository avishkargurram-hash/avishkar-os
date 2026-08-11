# Memory Framework

## Vision
`agent-factory`'s `InMemoryMemoryPolicy` was always a documented
placeholder — real memory needed to survive a process restart. Memory
Framework closes that gap: real, persistent implementations of the same
`avishkar_agent.MemoryPolicy` interface every Chief Domain Agent already
speaks, so no agent code changes when it moves from "works in this
process" to "remembers across sessions."

## Architecture
```
factories/memory-factory/
├── CONTRACT.md · schemas/memory-record.schema.json
└── python/avishkar_memory/
    ├── backends/file_backend.py    FileMemoryPolicy -- one JSON file per kind
    ├── backends/sqlite_backend.py  SQLiteMemoryPolicy -- one table, stdlib sqlite3
    └── factory.py                  build_memory_policy(config) -- resolves a
                                     blueprint's memory_policy.backend to a real instance
```
Both backends implement `avishkar_agent.MemoryPolicy` verbatim (no new
interface — see [CONTRACT.md](./CONTRACT.md)) and are genuinely different
persistence strategies, the same "prove the abstraction is real" bar
Router (two model providers) and Universal Integration (two protocol
adapters) already set.

## Folder Structure / Naming Standards
See tree above; follows [STANDARDS.md](../../STANDARDS.md) §3.
Backends are `<name>_backend.py` / `<Name>MemoryPolicy`.

## Interfaces
`FileMemoryPolicy(root_dir)`, `SQLiteMemoryPolicy(db_path=":memory:")` —
both: `.remember(kind, key, value)`, `.recall(kind, key)`,
`.forget(kind, key)`, `.list_keys(kind)` (extra, beyond the interface).
`build_memory_policy(config, *, root_dir=, db_path=) -> MemoryPolicy`.
Full contract: [CONTRACT.md](./CONTRACT.md).

## Extension Model
A new backend implements `avishkar_agent.MemoryPolicy` and adds one
branch to `build_memory_policy` — no other file changes.

## Examples
`python factories/memory-factory/examples/quickstart.py` — both
backends, `build_memory_policy` resolving a blueprint, and a real
`ChiefDomainAgent` using persistent memory end to end.

## Best Practices
- Use `FileMemoryPolicy` for human-inspectable, low-volume state (agent
  preferences, small fact stores); `SQLiteMemoryPolicy` once query volume
  or concurrent access matters.
- Keep `db_path=":memory:"` for tests/examples — never assert on a real
  file path outside a `tempfile` context.

## Anti-Patterns
- Reimplementing `remember`/`recall`/`forget` inside a Chief Domain
  Agent's own domain module instead of adding a backend here — the whole
  point of `MemoryPolicy` being agent-factory's public interface is that
  every backend is interchangeable without touching agent code.
- Storing secrets in any memory kind (STANDARDS.md §6 — unchanged by
  which backend persists it).

## Testing Strategy
24 tests: one shared contract-test mixin (`_MemoryPolicyContractTests`)
exercised against both backends identically, plus backend-specific
persistence tests (reopening a file dir / reconnecting to a sqlite file)
and `build_memory_policy` resolution tests for all three config values.

## Limitations
- No encryption at rest for either backend — sensitive values shouldn't
  be stored here yet (see Anti-Patterns).
- No TTL/expiry policy — `episodic` memories accumulate indefinitely;
  retention policy is a Future Roadmap item, same gap `memory-factory`'s
  original placeholder README already flagged.
- Both backends are now thread-safe **within a single process**
  (Avishkar OS Phase 17.4 hardening, ADR-0024): `FileMemoryPolicy` and
  `SQLiteMemoryPolicy` each gained an internal lock closing real races
  in their read-modify-write operations (`FileMemoryPolicy`'s in
  particular was a genuine silent-data-loss bug, not just a
  theoretical one — concurrent `remember()` calls for different keys
  in the same kind file could lose one entirely). Neither is safe for
  **concurrent writers across multiple OS processes** — no file
  locking (`FileMemoryPolicy`) or WAL-mode coordination
  (`SQLiteMemoryPolicy`) is implemented; a multi-process/multi-worker
  deployment needs external coordination this framework doesn't
  provide.

## Future Roadmap
- Retention/expiry policies (PII-aware) per STANDARDS.md's original
  aspiration for this framework.
- A vector-backed `semantic` kind for similarity search once a real
  embedding workflow exists (ties to Knowledge Framework, Phase 6).
- Encryption-at-rest for `FileMemoryPolicy`.
