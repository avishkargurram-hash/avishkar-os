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

## Phase 5 — Memory Framework (`memory-factory`) — ✅ LOCKED (2026-08-09)

- ✅ `CONTRACT.md` + schema; reuses `avishkar_agent.MemoryPolicy`
  verbatim rather than redefining it (ADR-0011 precedent)
- ✅ Two real backends: `FileMemoryPolicy` (JSON per kind, durable),
  `SQLiteMemoryPolicy` (stdlib `sqlite3`) — both stdlib-only
- ✅ `build_memory_policy()` closes the seam `agent-factory` left open
  since Phase 3 — any blueprint's `memory_policy.backend` now resolves
  to a real, persistent instance with zero agent-factory changes
- ✅ 24 tests (one shared contract mixin run against both backends),
  runnable example, README documented to the Framework template

Entered under Execution Mode (ADR-0012) — from here through Phase 15,
ROADMAP entries stay terse; full narrative detail lives in each phase's
commit message and README.

## Phase 6 — Knowledge Framework (`knowledge-factory`) — ✅ LOCKED (2026-08-09)

- ✅ `CONTRACT.md` + schema; ingest → chunk → embed → index → retrieve
  pipeline, stdlib-only and offline (`avishkar_agent.Tool` reused via
  `as_tool()`, ADR-0011 precedent)
- ✅ `chunk_text()` (overlapping word chunks), `HashingEmbedder`
  (deterministic `zlib.crc32` feature hashing — not Python's randomized
  `hash()`), `VectorIndex` (cosine similarity), `KnowledgeBase`
  (ingest/search façade)
- ✅ `as_tool(kb)` closes the seam so any `ChiefDomainAgent` can register
  a knowledge base as a callable tool with zero agent-factory changes
- ✅ 20 tests, runnable example (caught and documented a real
  `HashingEmbedder` ranking-quality limitation on common-word queries
  rather than hiding it), README documented to the Framework template
  including an honest Limitations section

## Phase 7 — Workflow Framework (`workflow-factory`) — ✅ LOCKED (2026-08-09)

Goal: compose agents, memory, and knowledge into repeatable multi-step
processes — deliberately sequenced after all three exist to compose.

- ✅ `CONTRACT.md` + schema; `WorkflowSpec`/`Step`/`WorkflowEngine` —
  plain-callable step engine, LangGraph node-shaped, zero
  `langgraph`/`n8n` dependency (`langgraph-factory`/`n8n-factory` stay
  deferred, ADR-0013)
- ✅ Linear + branching control flow, per-step retry (`RetryPolicy`
  reused from `avishkar_integration`, third reuse of that type), a
  cycle guard (`max_steps`)
- ✅ Three real bridges closing the composition seam with zero changes
  to agent-factory/memory-factory/knowledge-factory: `make_agent_step`,
  `make_knowledge_search_step`, `make_memory_read_step`/
  `make_memory_write_step`
- ✅ 17 tests, a runnable 5-step example (search knowledge → ask agent →
  extract → remember, verified end to end), README documented to the
  Framework template

## Phase 8 — Prompt Framework (`prompt-factory`) — ✅ LOCKED (2026-08-09)

Product-enablement polish. Versioned, evaluable prompt assets — split
from the original combined "Phase 8" per the Execution Mode phase list
(ADR-0012); Template and Starter Kit each get their own phase below so
each still gets a real contract/tests/example, not a shared placeholder.

- ✅ `CONTRACT.md` + schema; `PromptVersion` (validated at construction —
  every `{var}` in `template` must be declared), `render()`,
  `PromptRegistry` (versioned, immutable-once-registered)
- ✅ Scoring seam (`Scorer` callable) + two real scorers
  (`exact_match_scorer`, `keyword_presence_scorer`) + `evaluate_version`/
  `compare_versions` — documented as forward-compatible with Phase 11's
  Evaluation Framework rather than blocking on it
- ✅ No new agent-factory bridge needed — a rendered prompt is a `str`,
  which `Task.input` already accepts (Phase 3, locked)
- ✅ 24 tests, a runnable example (evaluate two prompt versions, pick
  the winner, feed it to a real `ChiefDomainAgent`), README documented
  to the Framework template

## Phase 9 — Template Framework (`template-factory`) — ✅ LOCKED (2026-08-09)

- ✅ `CONTRACT.md`; `TemplateFile` wraps `avishkar_prompt.PromptVersion`
  directly rather than redefining a parallel type (ADR-0015),
  `Template` (validated unique file paths), `TemplateRegistry`
  (mirrors `PromptRegistry`)
- ✅ `instantiate()` — writes a Template to a real target directory,
  validates every target path before writing any file (no partial
  writes on collision), never overwrites without `overwrite=True`
- ✅ `MODULE_README_TEMPLATE` — STANDARDS.md §2.1's Module template
  formalized as a real, instantiable `Template`, not left as unenforced
  prose
- ✅ 15 tests, a runnable example (instantiate the built-in template for
  a real new package, then a custom two-file project skeleton), README
  documented to the Framework template

## Phase 10 — Starter Kit Framework (`starter-kit-factory`) — ✅ LOCKED (2026-08-09)

- ✅ `CONTRACT.md`; `StarterKit` composes a real `AgentBlueprint`
  (portable JSON) with generated *source code* (`main.py` via
  `template-factory`) rather than serialized runtime objects (ADR-0016)
- ✅ `StarterKitRegistry` (mirrors Prompt/TemplateRegistry),
  `materialize()` (writes project files + `agent/blueprint.json`,
  all-or-nothing on collision, reuses `template-factory`'s
  `instantiate()` and `TemplateInstantiationError` verbatim)
- ✅ `AGENT_WITH_MEMORY_AND_KNOWLEDGE` — one real, generic, working kit
  (agent + memory + knowledge + workflow); deliberately not a
  named-product kit — see ADR-0016 for why "first real product" wasn't
  delivered as originally phrased
- ✅ 12 tests, a runnable example that materializes the kit **and
  actually runs the generated `main.py` as a subprocess** (exit 0, real
  output), README documented to the Framework template

## Phase 11 — Evaluation Framework (`evaluation-factory`) — ✅ LOCKED (2026-08-09)

Un-deferred from ADR-0009's list per the Execution Mode phase order —
the minimal Phase 3 harness (agent self-evaluation) becomes the full
framework: scorers, regression suites, eval-as-CI for any agent/
workflow/prompt/template built above.

- ✅ `CONTRACT.md`; `EvalSuite` + `run_suite()`/`passes_threshold()` —
  reuses `EvalCase`/`EvalReport`/`RegressionResult`/`Scorer` from
  `prompt-factory` verbatim (closes ADR-0014's seam, ADR-0017), one
  canonical scoring vocabulary for prompts/agents/workflows
- ✅ Two more real scorers (`length_bounds_scorer`,
  `weighted_keyword_scorer`)
- ✅ `make_quality_gate()` — produces a real `avishkar_agent.QualityGate`
  from an `EvalSuite`, closing the loop into Phase 3's existing
  `quality_gates=` seam with zero agent-factory changes (ADR-0017)
- ✅ `evaluate_workflow_result()` — scores a `WorkflowResult`
- ✅ 16 tests, a runnable example with a real `ChiefDomainAgent` whose
  `QualityGate` is built by this framework (not hand-written), README
  documented to the Framework template

## Phase 12 — Security Framework (`security-factory`) — ✅ LOCKED (2026-08-09)

Also un-deferred from ADR-0009's list per the Execution Mode phase
order — guardrail templates, threat-model checklist, and a retroactive
review pass across everything built in Phases 1–11.

- ✅ `CONTRACT.md`; `scan_for_secrets`/`redact_secrets`/
  `scan_repository_for_secrets` — real, automated regex-based secret
  detection, kept explicitly separate from human-judgment review
  (ADR-0018)
- ✅ `SECURITY_CHECKLIST` (10 fixed items from STANDARDS.md §6) +
  `run_checklist()` — a structured self-assessment, not claimed to be
  automated verification
- ✅ Three real `avishkar_agent.Guardrail` bridges
  (`make_secret_scanning_guardrail`, `make_rate_limit_guardrail` with a
  real sliding-window limiter, `make_input_validation_guardrail`) —
  zero agent-factory changes
- ✅ **Retroactive review actually run**: `scan_repository_for_secrets()`
  executed against the whole repository in this phase's own example —
  zero real findings (only the example's own well-known-fake AWS
  placeholder and this framework's deliberately-fake test fixtures)
- ✅ 24 tests, a runnable example, README documented to the Framework
  template

## Phase 13 — Remaining 10 Chief Domain Agents — 🚧 IN PROGRESS (2026-08-09)

The other 10 seats in ADR-0007's locked 11-agent roster (agent-factory,
Phase 3, built the first), each to the 30-section template (ADR-0010),
each wiring at least one real Phase 5–12 framework integration (not
just declared seams like Phase 3's agent had to use):

- ✅ Medical & Healthcare — `SQLiteMemoryPolicy`, a real `KnowledgeBase`,
  a `make_quality_gate()`-built gate, `make_secret_scanning_guardrail()`
- ✅ Legal & Compliance — `FileMemoryPolicy` (cross-instance persistence
  verified), a real `KnowledgeBase`, same evaluation/security bridges
- ✅ Startup, Business & Product — `SQLiteMemoryPolicy`, a real
  `KnowledgeBase`, same evaluation/security bridges
- ✅ Education & Knowledge — `FileMemoryPolicy`, a real `KnowledgeBase`,
  same evaluation/security bridges
- ✅ Research & Intelligence — `SQLiteMemoryPolicy`, a real
  `KnowledgeBase`, same evaluation/security bridges
- ✅ Finance & Economics — `FileMemoryPolicy`, a real `KnowledgeBase`,
  `make_rate_limit_guardrail()` (proven with a real integration test)
- ✅ Government & Public Policy — `SQLiteMemoryPolicy`, a real
  `KnowledgeBase`, same evaluation/security bridges
- ✅ Human Development & Psychology — `FileMemoryPolicy`, a real
  `KnowledgeBase`, and `crisis-escalation`: this repository's most
  safety-critical guardrail, whose block reason carries real 988
  crisis-resource contact information (verified by test)
- ✅ Creative & Media — `SQLiteMemoryPolicy`, a real `KnowledgeBase`,
  same evaluation/security bridges
- 💤 Orchestrator (composes `avishkar_agent.Orchestrator` over all 11)

## Phase 14 — Knowledge Library

Populate every framework with reusable assets: templates, workflows,
checklists, standards, examples — a breadth pass across what Phases
1–13 built, not new architecture.

## Phase 15 — Final Integration

Connect every framework into one production-ready Avishkar OS; verify
every framework integrates with Core Engine, AI Router, Universal
Integration, Agent Framework, Memory, Knowledge, Workflow, Evaluation,
and Security.

## Deferred — not yet scheduled (ADR-0009)

Not silently dropped, not silently assigned an order — these get a slot
via a future ADR when the platform is ready to schedule them:

- `langgraph-factory` (LangGraph Framework)
- `n8n-factory` (Automation Framework)
- `project-factory` (Project Framework)
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
