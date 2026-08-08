# Changelog

All notable changes to Avishkar OS are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning
follows [Semantic Versioning](https://semver.org/) once the platform has
its first consumer.

## [Unreleased]

### Added
- Initial repository scaffold: root governance docs (`README.md`,
  `ARCHITECTURE.md`, `STANDARDS.md`, `ROADMAP.md`, `DECISIONS.md`,
  `CONTRIBUTING.md`, `CLAUDE.md`), `LICENSE`, `.gitignore`.
- Directory structure for `factories/` (13 factories) and the library
  shelves (`agents/`, `templates/`, `workflows/`, `knowledge/`, `memory/`,
  `router/`, `mcp/`, `langgraph/`, `automation/`, `starters/`, `core/`),
  plus `docs/` — each with a README defining its contract.
- ADR-0001 through ADR-0004 recorded in `DECISIONS.md`.
- Reconciled repo against the Master Build Directive: added
  `factories/documentation-factory` (14th factory; 16 Frameworks total
  with `core/` and `router/`), a three-tier documentation template
  (Module / Framework / Chief Domain Agent — STANDARDS.md §2), and locked
  the Chief Domain Agent roster to 10 domains + Orchestrator
  (ARCHITECTURE.md §4). Recorded as ADR-0005 through ADR-0007.
- **Core Engine Framework — Phase 1 locked** (ADR-0008): language-agnostic
  contract (`core/CONTRACT.md`, `core/schemas/*.json`) plus a Python
  reference implementation (`core/python/avishkar_core/`, zero
  third-party dependencies) providing Config, Logger, EventBus, and
  ModuleRegistry. 47 passing unit tests and a runnable end-to-end example
  (`core/examples/quickstart.py`). `core/README.md` rewritten to the
  Framework documentation template.
- **Build order reordered** (ADR-0009): explicit user-directed sequence —
  Router → Agent (11 Chief Domain Agents) → MCP → Memory → Knowledge →
  Workflow → Prompt/Template/Starter Kit — supersedes the earlier Phase
  2/3 thematic grouping in `ROADMAP.md`. `langgraph-factory`,
  `n8n-factory`, `project-factory`, `evaluation-factory`,
  `security-factory`, `documentation-factory` marked deferred, not
  silently ordered.
- **AI Router Framework — Phase 2 locked**: language-agnostic contract
  (`router/CONTRACT.md`, `router/schemas/*.json`) plus a Python reference
  implementation (`router/python/avishkar_router/`) — `Router`,
  `RoutingPolicy`/`RoutingRule` (capability/task-type matching, explicit
  model requests skip fallback), `CostTracker`, a normalized
  `ProviderError` hierarchy, `MockProvider` (network-free) and
  `AnthropicProvider` (real adapter over the official `anthropic` SDK;
  Opus 5 / Sonnet 5 / Haiku 4.5 catalog). 42 passing unit tests and a
  runnable end-to-end example (`router/examples/quickstart.py`).
  `router/README.md` documented to the Framework template with an honest
  Limitations section.
- **ADR-0010**: Chief Domain Agent template expanded from 18 to 30
  sections (STANDARDS.md §2.3), superseding ADR-0006 for the agent tier
  only, per explicit user direction that a Chief Domain Agent must be "a
  complete software system, not a prompt."
- **Agent Framework — Phase 3 engine locked**: language-agnostic contract
  (`factories/agent-factory/CONTRACT.md`, `schemas/*.json`) plus a Python
  reference implementation (`avishkar_agent`) — `ChiefDomainAgent`
  (plan-act-reflect reasoning loop with guardrails, quality gates, a
  human-in-the-loop `ApprovalGate`, sub-agent role routing),
  `Orchestrator` (single/hierarchical/swarm dispatch, pluggable conflict
  resolution), `MemoryPolicy`, `ToolRegistry` with typed `MCPToolRef`
  placeholders, 4 `ThinkingModel` strategies, and a 3-file
  `scaffold_agent()` generator. 71 passing unit tests and a runnable
  end-to-end example. `agent-factory/README.md` documented to the
  Framework template.
- **First Chief Domain Agent built: `agents/software-ai-engineering/`**
  — full 30-section README, 2 real tools, 2 guardrails, 2 quality gates,
  4 absorbed sub-agent roles, 19 passing tests, a runnable example. A
  real sub-agent-routing bug (hyphen normalization) was caught by that
  example and fixed with a regression test in `agent-factory` itself.
  Remaining 10 roster entries (ADR-0007) follow one at a time.
- **ADR-0011**: `mcp-factory` rescoped from a narrow MCP-server generator
  to the Universal Integration Framework — a protocol-agnostic tool
  platform with MCP as its first-class implementation, per explicit user
  direction. Folder/slot unchanged; LangGraph integration ships as
  dependency-free node functions (no `langgraph` import, `langgraph-factory`
  stays deferred); Agent Framework integration ships as a new bridge
  module consuming `agent-factory`'s existing public types, with
  `agent-factory`'s own source untouched.
- **Universal Integration Framework — Phase 4 locked**: language-agnostic
  contract (`mcp-factory/CONTRACT.md`, `schemas/*.json`) plus a Python
  reference implementation (`avishkar_integration`) — the 12-field
  universal `ToolContract`, `ProtocolAdapter` abstraction,
  `UniversalToolRegistry`, `ToolRuntime` (retries, access control,
  sandbox-trust denial, human-in-the-loop approval reusing
  `avishkar_agent.ApprovalGate`, metrics, memory integration, events),
  `IntegrationPlanner` (delegates model selection to AI Router), an
  Agent Framework bridge, and 6 LangGraph-shaped node functions. Two
  real `ProtocolAdapter`s: `MCPAdapter` (official `mcp` SDK) and
  `RESTAdapter` (stdlib only). 70 passing unit tests and a runnable
  end-to-end example that caught and fixed two real bugs (a protocol/
  adapter mismatch now a hard `ProtocolMismatchError`, and an
  approval-gate callback that couldn't see actual call arguments), both
  regression-tested. `mcp-factory/README.md` documented to the Framework
  template plus Contracts/Testing Strategy/Extension Guide/Troubleshooting.

- **ADR-0012**: Execution Mode entered for Phases 5–15 (continuous,
  unattended, pausing only for decisions genuinely requiring approval).
  Confirmed the Phase 13 agent roster stays at 11 ("Science" = "Research
  & Intelligence" renamed, not a 12th domain; ADR-0007 unchanged).
- **Memory Framework — Phase 5 locked**: `avishkar_memory` — two real,
  stdlib-only `avishkar_agent.MemoryPolicy` backends
  (`FileMemoryPolicy`, `SQLiteMemoryPolicy`) and `build_memory_policy()`,
  closing the persistent-memory seam `agent-factory` left open since
  Phase 3 with zero changes to `agent-factory`'s own source. 24 tests, a
  runnable example wiring a real `ChiefDomainAgent` to persistent memory.
- **Knowledge Framework — Phase 6 locked**: `avishkar_knowledge` —
  stdlib-only ingest → chunk → embed → index → retrieve pipeline
  (`chunk_text`, `HashingEmbedder` using deterministic `zlib.crc32`
  feature hashing, `VectorIndex` cosine search, `KnowledgeBase`) plus
  `as_tool()` wrapping any knowledge base as a real
  `avishkar_agent.Tool`. 20 tests, a runnable example that surfaced and
  documented a genuine `HashingEmbedder` ranking-quality limitation on
  common-word-heavy queries rather than hiding it (see
  `knowledge-factory/README.md` Limitations).
- **ADR-0013**: `workflow-factory` ships a plain-callable step engine
  instead of un-deferring `langgraph-factory`/`n8n-factory`; `RetryPolicy`
  reused from `avishkar_integration` for the third time.
- **Workflow Framework — Phase 7 locked**: `avishkar_workflow` —
  `WorkflowSpec`/`Step`/`WorkflowEngine`, a validated, retryable,
  branch-capable step engine whose steps are LangGraph-node-shaped
  callables, plus three bridges (`make_agent_step`,
  `make_knowledge_search_step`, `make_memory_read_step`/
  `make_memory_write_step`) composing agent-factory, knowledge-factory,
  and memory-factory with zero changes to any of their locked source.
  17 tests, a runnable example wiring a real `ChiefDomainAgent`,
  `KnowledgeBase`, and `InMemoryMemoryPolicy` into one 5-step workflow.

[Unreleased]: https://github.com/avishkar-labs/avishkar-os/compare/HEAD
