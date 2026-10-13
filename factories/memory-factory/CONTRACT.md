# Memory Framework — Language-Agnostic Contract

Mirrors [`core/CONTRACT.md`](../../core/CONTRACT.md) and siblings.
Python ships first ([`python/avishkar_memory/`](./python/avishkar_memory/)).

Per [DECISIONS.md](../../DECISIONS.md) ADR-0011's precedent (a later
framework depends on an earlier one's public types rather than
duplicating them): `MemoryPolicy` the interface is **not redefined
here** — it's `avishkar_agent.MemoryPolicy` (agent-factory CONTRACT.md
§3), already public, already what every Chief Domain Agent's Memory
Policies (agent template §8) resolves against. This framework's job is
providing **real, persistent implementations** of that interface —
`agent-factory`'s own `InMemoryMemoryPolicy` was always documented as a
placeholder pending this framework (agent-factory/README.md Future
Roadmap: "Persistent memory backends once memory-factory ships").

---

## 1. Backends

```
MemoryPolicy {                     # = avishkar_agent.MemoryPolicy, reused verbatim
  remember(kind, key, value) -> void
  recall(kind, key) -> any | null
  forget(kind, key) -> void
}
# kind ∈ {"short_term", "long_term", "episodic", "semantic"}
```

Shipped in v1:

- **`FileMemoryPolicy(root_dir)`** — one JSON file per kind under
  `root_dir`, human-inspectable, durable across process restarts.
- **`SQLiteMemoryPolicy(db_path)`** — a single `memory(kind, key, value)`
  table via stdlib `sqlite3`; `db_path=":memory:"` for process-local
  (test/example default), a real file path for durability.

Both are genuinely different persistence strategies, not one
implementation renamed twice — the same "prove the abstraction is real"
bar Router (two providers) and Universal Integration (two protocol
adapters) already set.

---

## 2. build_memory_policy — closing the Agent Framework seam

```
build_memory_policy(config: avishkar_agent.MemoryPolicyConfig, *,
                     root_dir: path | null = null,
                     db_path: string | null = null) -> MemoryPolicy
  throws UnknownBackendError
  # config.backend: "in_memory" -> avishkar_agent.InMemoryMemoryPolicy
  #                 "file"      -> FileMemoryPolicy
  #                 "sqlite"    -> SQLiteMemoryPolicy
```

Any `AgentBlueprint.memory_policy.backend` value a domain module already
declares (agent-factory CONTRACT.md §2) resolves through this function —
no change to `agent-factory`'s source, the same integration shape
`mcp-factory`'s `agent_bridge.py` established.

---

## Cross-cutting rules

- **Depends on Core Engine (`Logger`) and Agent Framework
  (`MemoryPolicy`, `MemoryPolicyConfig`) only.**
- **Adding a new backend never changes `build_memory_policy`'s callers**
  — only a new `backends/*.py` file implementing `MemoryPolicy`, plus one
  new branch in `build_memory_policy`.
