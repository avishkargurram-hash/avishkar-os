# Roadmap

Status legend: ✅ Built · 🚧 In progress · 📋 Planned · 💤 Not started

This roadmap tracks the platform itself, not any single product built on
top of it. Update it when a phase's status actually changes — not on a
schedule.

## Execution mode: one framework at a time

Per the Master Build Directive (2026-08-08): frameworks are built
completely, one at a time — not scaffolded in parallel. For each
framework: build it fully to the [STANDARDS.md](./STANDARDS.md) §2.2
template (or §2.3 for each Chief Domain Agent) with real, working code and
examples → review → refine → lock (mark ✅ here) → only then start the
next. A framework isn't ✅ until its Limitations section is honest and its
Examples actually run.

## Phase 0 — Foundation (current)

Goal: a repository that can't be built on top of by mistake, because its
contracts are written down before its code is.

- ✅ Repository structure, standards, architecture, decision log
- ✅ `CLAUDE.md` master constitution
- ✅ Per-module README contracts (purpose stated, implementation pending)
- ✅ Reconciled against the Master Build Directive: Documentation
  Framework added (ADR-0005), three-tier doc templates (ADR-0006), Chief
  Domain Agent roster locked at 10 + Orchestrator (ADR-0007)
- 💤 CI scaffold (lint, type-check, test, doc-coverage gate)
- 💤 `CONTRIBUTING.md` workflow validated with a real first PR

## Phase 1 — Core Engine Framework (`core/`) — ✅ LOCKED (2026-08-08)

Goal: build the one framework everything else depends on, completely,
before anything else starts — nothing after this phase can be genuinely
"done" without it, since every other framework's README declares a
dependency on it.

- ✅ `CONTRACT.md` + `schemas/`: the language-agnostic contract (ADR-0008)
- ✅ `python/avishkar_core/`: Config, Logger, EventBus, ModuleRegistry —
  stdlib-only, zero third-party dependencies
- ✅ 47 unit tests, all passing (`core/python/tests/`, run via
  `python -m unittest discover -s tests` with `PYTHONPATH=core/python`)
- ✅ `core/README.md` documented to the Framework template (STANDARDS.md
  §2.2) with real Interfaces
- ✅ Runnable end-to-end example: `core/examples/quickstart.py`
- 💤 Second-language (TypeScript) implementation — deferred, not blocking
  (see `core/README.md` Future Roadmap)

Per **ADR-0009**, the build order below is the explicit, user-directed
sequence — superseding the earlier Phase 2/3 grouping. It is a flat list
of individually-locked phases, not thematic bundles: each phase is one
framework, built completely before the next starts.

## Phase 2 — AI Router Framework (`router/`) — ✅ LOCKED (2026-08-08)

Goal: the single place that decides which model/provider handles a
request — must exist before Agent Framework, since every Chief Domain
Agent routes its model calls through it.

- ✅ `CONTRACT.md` + `schemas/`: language-agnostic contract (types,
  ModelProvider interface, RoutingPolicy, Router)
- ✅ `python/avishkar_router/`: `Router`, `RoutingPolicy` +
  `RoutingRule` (capability/task-type matching, explicit-model-skips-
  fallback), `CostTracker`, normalized `ProviderError` hierarchy
- ✅ `MockProvider` (network-free, for tests/examples) and
  `AnthropicProvider` (real adapter over the official `anthropic` SDK,
  3-model catalog: Opus 5 / Sonnet 5 / Haiku 4.5)
- ✅ 42 unit tests, all passing (`router/python/tests/`); error
  normalization tested against the real `anthropic` SDK's exception
  classes (constructed directly, no network call)
- ✅ `router/README.md` documented to the Framework template, honest
  Limitations (no sampling params, text-only messages, no budget
  enforcement, no streaming, no live network call exercised here)
- ✅ Runnable end-to-end example: `router/examples/quickstart.py`
  (policy routing, fallback, explicit-model behavior, cost tracking)
- 💤 A second provider adapter (OpenAI/Google) — deferred until a real
  caller needs multi-vendor routing (see `router/README.md` Future
  Roadmap)

## Phase 3 — Agent Framework (`agent-factory`) — engine ✅ LOCKED, roster 🚧 1/11

Goal: prove the Factory → Library pattern (ADR-0002) end-to-end as a real
**runtime** (ADR-0010 — a Chief Domain Agent is a software system, not a
prompt), then build out the locked roster (ARCHITECTURE.md §4 / ADR-0007)
one at a time. The framework itself (below) is complete and locked; this
phase as a whole stays 🚧 until all 11 roster entries exist.

- ✅ `CONTRACT.md` + `schemas/`: language-agnostic contract (Task,
  AgentBlueprint, AgentResult, ChiefDomainAgent, Orchestrator)
- ✅ `python/avishkar_agent/`: `ChiefDomainAgent` (plan-act-reflect
  reasoning loop, guardrails, quality gates, human-in-the-loop
  `ApprovalGate`, sub-agent role routing), `Orchestrator`
  (route/delegate_team/broadcast/resolve_conflict — single, hierarchical,
  swarm, conflict resolution), `MemoryPolicy` (+ `InMemoryMemoryPolicy`
  reference impl), `ToolRegistry` (+ typed `MCPToolRef` placeholders),
  4 `ThinkingModel` strategies, `scaffold_agent()` generator (3 files,
  never "hundreds")
- ✅ ADR-0010: Chief Domain Agent template expanded 18 → 30 sections,
  superseding ADR-0006 for the agent tier only
- ✅ 71 unit tests, all passing (`factories/agent-factory/python/tests/`)
- ✅ `agent-factory/README.md` documented to the Framework template
- ✅ Runnable end-to-end example: `agent-factory/examples/quickstart.py`
  (two toy agents, guardrail block, HITL approval, Orchestrator routing/
  team/broadcast/conflict-resolution)
- ✅ **First Chief Domain Agent built: `agents/software-ai-engineering/`**
  — full 30-section README, 2 real tools (`static_check`,
  `estimate_complexity`), 2 guardrails, 2 quality gates, 4 absorbed
  sub-agent roles, 19 passing tests, runnable example. A real bug
  (sub-agent hyphen-normalization) was caught by the example and fixed
  with a regression test in `agent-factory` itself.
- 💤 `evaluation-factory` integration for a real eval harness (currently
  hand-written `QualityGate` callables — see agent's README §16)
- 💤 Remaining 9 Chief Domain Agents + a dedicated Orchestrator agent
  package, one at a time — order driven by which product needs which
  domain first, not alphabetically

## Phase 4 — Universal Integration Framework (`mcp-factory`) — ✅ LOCKED (2026-08-09)

Goal: give agents a standard, protocol-agnostic way to reach tools —
needed before Memory and Knowledge, since a memory/knowledge backend is
itself exposed to agents as tool access. Rescoped from a narrow "MCP
server generator" to a real integration platform per explicit user
direction — see [DECISIONS.md](./DECISIONS.md) ADR-0011.

- ✅ `CONTRACT.md` + `schemas/`: language-agnostic contract (ToolContract,
  ProtocolAdapter, UniversalToolRegistry, ToolRuntime, IntegrationPlanner)
- ✅ `python/avishkar_integration/`: `ProtocolAdapter` abstraction,
  `UniversalToolRegistry` (with `ProtocolMismatchError` validation),
  `ToolRuntime` (retries, access control, sandbox-trust denial,
  human-in-the-loop approval via reused `avishkar_agent.ApprovalGate`,
  `MetricsCollector`, `MemoryPolicy` integration, EventBus events),
  `IntegrationPlanner` (AI Router integration — best tool + delegated
  best model), Agent Framework bridge (`resolve_mcp_tool_ref`,
  `request_capability`), `langgraph_nodes` (6 dependency-free,
  LangGraph-shaped node functions)
- ✅ Two real `ProtocolAdapter`s: `MCPAdapter` (official `mcp` SDK,
  lazily imported) and `RESTAdapter` (stdlib `urllib` only) — proving
  the abstraction is genuine, not an MCP-shaped wrapper
- ✅ 70 unit tests, all passing, both adapters tested via dependency
  injection (fake MCP session / fake HTTP transport), no live network
- ✅ `mcp-factory/README.md` documented to the Framework template plus
  the user's explicit doc list (Contracts, Testing Strategy, Extension
  Guide, Troubleshooting), honest Limitations
- ✅ Runnable end-to-end example: `mcp-factory/examples/quickstart.py`
  — caught and fixed two real bugs (a protocol/adapter mismatch now a
  hard error, and an approval-gate callback that couldn't see actual
  call arguments), both regression-tested
- 💤 GraphQL, Python SDK, CLI, Database, Filesystem, Webhook adapters —
  documented extension points (README.md Extension Guide), not
  scaffolded, built when a real product needs one
- 💤 Rate-limit enforcement, MCP session pooling, real sandboxing — see
  README.md Future Roadmap

## Phase 5 — Memory Framework (`memory-factory`)

- 💤 Storage-agnostic memory interface (short-term, long-term, episodic)
- 💤 First shared memory backend in `memory/`

## Phase 6 — Knowledge Framework (`knowledge-factory`)

- 💤 Retrieval pipeline contract (ingest → chunk → embed → index)
- 💤 First shared knowledge base in `knowledge/`

## Phase 7 — Workflow Framework (`workflow-factory`)

Goal: compose agents, memory, and knowledge into repeatable multi-step
processes — deliberately sequenced after all three exist to compose.

- 💤 Workflow spec (steps, branching, error/retry policy)
- 💤 First reusable workflow in `workflows/`

## Phase 8 — Prompt + Template + Starter Kit Frameworks

Product-enablement polish, built last because it packages everything
above for a new product to consume.

- 💤 `prompt-factory` + `template-factory` producing versioned, evaluable
  assets
- 💤 `starter-kit-factory` + first starter kit in `starters/`
- 💤 First real product (candidate: whichever of Tryvanta / Humanify OS /
  GENESIS / Muziclly / AI Atlas / Coupler is nearest to build) scaffolded
  from a starter kit and running on Avishkar OS

## Deferred — not yet scheduled (ADR-0009)

Not silently dropped, not silently assigned an order — these get a slot
via a future ADR when the platform is ready to schedule them:

- `langgraph-factory` (LangGraph Framework)
- `n8n-factory` (Automation Framework)
- `project-factory` (Project Framework)
- `evaluation-factory` beyond its Phase 3 minimal harness (full Evaluation
  Framework)
- `security-factory` (Security Framework) — guardrail templates,
  threat-model checklist, retroactive review of everything built above
- `documentation-factory` (Documentation Framework) — doc-coverage lint,
  ADR tooling, retroactive template-conformance check

## Explicitly out of scope for Avishkar OS

- Any product-specific business logic, UI, or customer-facing surface —
  those live in product repos.
- Hosting/infra provisioning for products — a candidate for a future
  `infra-factory` if the need proves reusable across products, not before.

## How this roadmap changes

A phase only moves to 🚧 when someone is actively working it, and only to
✅ when its module's README (per STANDARDS.md's template) is accurate and
its Limitations section is honest. Reordering phases or adding a new
factory requires an ADR in [DECISIONS.md](./DECISIONS.md) first.
