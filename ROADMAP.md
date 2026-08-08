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

## Phase 3 — Agent Framework (`agent-factory`) — the 11 Chief Domain Agents begin

Goal: prove the Factory → Library pattern (ADR-0002) end-to-end, then
build out the locked roster (ARCHITECTURE.md §4 / ADR-0007) one at a time.

- 💤 `agent-factory`: blueprint schema, CLI scaffold
- 💤 First Chief Domain Agent built completely to the §2.3 template
  (candidate: Software & AI Engineering — nearest to this platform's own
  needs) landing in `agents/`, routed through `router/`
- 💤 `evaluation-factory`: minimal harness to eval that first agent
- 💤 Remaining 9 Chief Domain Agents + Orchestrator, one at a time —
  order driven by which product needs which domain first

## Phase 4 — MCP Framework (`mcp-factory`)

Goal: give agents a standard way to reach tools — needed before Memory
and Knowledge, since a memory/knowledge backend is itself exposed to
agents as tool access.

- 💤 MCP server generator + security-checklist-by-default scaffolding
- 💤 First reusable MCP server in `mcp/`

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
