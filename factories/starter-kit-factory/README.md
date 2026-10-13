# Starter Kit Framework

## Vision
Getting from "nothing" to "a working product shape running on Avishkar
OS" shouldn't require assembling eight frameworks from scratch. Starter
Kit Framework composes them into one clone-and-go kit: a real
`AgentBlueprint`, written as portable JSON, plus a real, runnable
project (`main.py`, `pyproject.toml`, `README.md`) that wires an agent,
memory, knowledge, and a workflow together using this platform's actual
APIs — generated code that runs, not a frozen snapshot pretending to.

## Architecture
```
factories/starter-kit-factory/python/avishkar_starter_kit/
├── types.py         StarterKit (blueprint + project_template + components) / StarterKitResult
├── registry.py        StarterKitRegistry -- same shape as Prompt/TemplateRegistry
├── materialize.py       materialize(kit, target_dir, values) -> written paths
└── builtin.py             AGENT_WITH_MEMORY_AND_KNOWLEDGE -- a real, working kit
```
See [CONTRACT.md](./CONTRACT.md) §0 for why a `StarterKit` composes a
real `AgentBlueprint` (portable data) with generated *source code*
(`main.py`) rather than trying to serialize live runtime objects
(a `WorkflowEngine` run, a `KnowledgeBase` instance) that can't
meaningfully cross a process boundary.

## Interfaces
`StarterKit(name, version, description, blueprint, project_template,
components=())`. `StarterKitRegistry().register(name, kit)` /
`.get(name, version=None)`. `materialize(kit, target_dir, values,
overwrite=False) -> StarterKitResult(written)`.

## Folder Structure / Naming Standards
See tree above; [STANDARDS.md](../../STANDARDS.md) §3.

## Extension Model
A new kit is a new `StarterKit`: an `AgentBlueprint` plus a
`template-factory` `Template` describing the project files to
generate. No base class, no plugin registration beyond
`StarterKitRegistry.register()`.

## Examples
`python factories/starter-kit-factory/examples/quickstart.py` —
materializes `AGENT_WITH_MEMORY_AND_KNOWLEDGE` into a real temporary
directory, then **actually runs the generated `main.py` as a
subprocess** (not just a syntax check) and prints its real output —
the strongest form of this repo's "run it, don't just write it"
discipline applied to generated code, not just this framework's own.

## Best Practices
- Keep a starter kit's `blueprint.mission` and ingested example
  documents generic and clearly placeholder ("Replace this with real
  product knowledge") — a kit is a starting point, not a finished
  product masquerading as one.
- Test a new kit the same way this one is tested: materialize it, then
  actually run the generated code, not just assert the files exist.

## Anti-Patterns
- Trying to embed a live `WorkflowSpec` (with real Python closures) as
  a "portable" field on `StarterKit` — closures aren't serializable
  across a clone; the generated `main.py` builds its own `WorkflowSpec`
  at runtime instead. See CONTRACT.md §0.
- Shipping a kit whose generated code silently depends on secrets/
  credentials without saying so — `AGENT_WITH_MEMORY_AND_KNOWLEDGE`'s
  generated `main.py` uses `MockProvider` and says explicitly, in its
  own output, to replace it with a real provider.

## Testing Strategy
12 tests: `StarterKitRegistry` lifecycle (mirrors Prompt/
TemplateRegistry's own suites), `materialize()` (project files +
`agent/blueprint.json` written, the manifest round-trips through
`AgentBlueprint.from_file()` unchanged, overwrite refusal/acceptance
for the manifest specifically), and the built-in kit (materializes a
complete project, and — the strongest test — the generated `main.py`
actually `compile()`s as valid Python, not just renders as text).

## Limitations
- **One built-in kit today** — `agent-with-memory-and-knowledge`,
  deliberately generic. None of the six named Avishkar products
  (Tryvanta, Humanify OS, GENESIS, Muziclly, AI Atlas, Coupler) has a
  kit yet: which starter kit shape actually fits a given product is a
  business/product decision this platform-level framework has no basis
  to make unilaterally (CLAUDE.md's "no business logic in the
  platform" principle) — a real gap, not a hidden one.
- **No repo/CI bootstrapping** — `materialize()` writes a directory
  tree, not a git repository with a remote, CI config, or issue
  tracker. That's `project-factory`'s job (deferred, ADR-0009); see
  CONTRACT.md §4 for the boundary.
- **Generated `main.py` uses `MockProvider`** — a real product must
  swap in a real model provider before this does anything beyond the
  fixed demo string; the generated code says so in its own output.

## Future Roadmap
- Additional kits as real product needs are identified (a chat-with-
  memory kit, a multi-agent orchestration kit) — built when a concrete
  need exists, not speculatively.
- Once `project-factory` is scheduled (a future ADR, per ADR-0009), it
  becomes a thin consumer of `materialize()` plus repo/CI bootstrapping.
