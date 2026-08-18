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

## Phase 13 — Remaining 10 Chief Domain Agents — ✅ LOCKED (2026-08-09)

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
- ✅ Orchestrator — no `blueprint.json` by design (it composes, it
  doesn't reason); `build_executive_orchestrator()` wires the real
  `avishkar_agent.Orchestrator` (Phase 3) over live instances of all
  10 domain agents above. `route()`/`delegate_team()`/`broadcast()`/
  `resolve_conflict()` all exercised against real dispatched results,
  including a test proving every one of the 10 agents actually
  completes a task, not just constructs

All 11 ADR-0007 roster seats are now real, tested, documented Chief
Domain Agents. This is also a working preview of Phase 15 (Final
Integration): the Orchestrator's own example already demonstrates
Core, Router, Agent, Memory, Knowledge, Evaluation, and Security all
composed together and running.

## Phase 14 — Knowledge Library — ✅ LOCKED (2026-08-09)

Populate every framework with reusable assets: templates, workflows,
checklists, standards, examples — a breadth pass across what Phases
1–13 built, not new architecture. Three concrete, product-facing
shelf artifacts landed, one per shelf directory that previously held
only a README pointing at its owning factory:

- ✅ `knowledge/platform-standards/` — a real `KnowledgeBase` seeded
  with genuine `STANDARDS.md` excerpts (engineering principles,
  security checklist, naming conventions), importable by any product's
  agents. 4 tests, a runnable example.
- ✅ `workflows/cross-domain-review/` — a real, reusable two-agent
  `WorkflowSpec` (any two `ChiefDomainAgent`s), demonstrated composing
  `legal-compliance` + `finance-economics` into one synthesized
  summary. 3 tests, a runnable example using two real Phase 13 agents.
- ✅ `templates/framework-readme/` — formalizes STANDARDS.md §2.2's
  Framework template as a real, instantiable `Template`, closing
  `template-factory`'s own Future Roadmap item. 2 tests, a runnable
  example.

Checklists: `security-factory`'s `SECURITY_CHECKLIST` (Phase 12) is
already the real, reusable checklist this phase would otherwise add —
no duplicate built. `starters/` and `memory/` already had a real,
concrete instance before this phase (Phase 10's
`AGENT_WITH_MEMORY_AND_KNOWLEDGE`, Phase 5's two backends) and needed
no further population.

## Phase 15 — Final Integration — ✅ LOCKED (2026-08-09)

Connect every framework into one production-ready Avishkar OS; verify
every framework integrates with Core Engine, AI Router, Universal
Integration, Agent Framework, Memory, Knowledge, Workflow, Evaluation,
and Security.

- ✅ [`docs/final-integration.md`](./docs/final-integration.md) +
  [`docs/final-integration-verify.py`](./docs/final-integration-verify.py)
  — one real, runnable script exercising all nine named systems in a
  single workflow (a real `RESTAdapter` call through Universal
  Integration, feeding a real `ChiefDomainAgent` that already wires
  Memory/Knowledge/Evaluation/Security internally), with its actual
  captured output committed alongside the script that produced it
- ✅ Root `README.md` and `ARCHITECTURE.md` §7 Status sections updated
  from their initial-scaffold text to reflect the real, complete state
- ✅ ADR-0019 closes Execution Mode (ADR-0012), recording final
  metrics: 542 tests passing platform-wide, zero known regressions

**All 15 phases are now locked.** ADR-0009's four deferred frameworks
(`langgraph-factory`, `n8n-factory`, `project-factory`,
`documentation-factory`) remain explicitly deferred, each requiring
its own future ADR to schedule — see Deferred, below.

## Phase 16 — Layla (Personal Executive Intelligence) — ✅ LOCKED (2026-08-09)

A new top-level platform capability (ADR-0020), composed entirely from
existing frameworks' public contracts — zero parallel systems (see
`layla/CONTRACT.md` §0 for the full reuse map).

- ✅ 21 real modules: `StateMachine` (explicit lifecycle),
  `LaylaMemoryPolicy` (wraps `avishkar_agent.MemoryPolicy`, Phase 5),
  `ProjectStore`, `IntentInterpreter`, `ContextBuilder`, `risk`
  classification + `ApprovalManager` (reuses `ApprovalGate`, Phase 3),
  `CapabilityResolver` + `Planner`, `DelegationEngine` (wraps
  `Orchestrator`, Phase 3), `ResultValidator`/`ConflictResolver`
  (reuses `HashingEmbedder`, Phase 6)/`ExecutiveSynthesizer`,
  `Scheduler`, `AuditLogger`/`SessionManager` (durable, restart-safe),
  `NotificationManager`/`HealthMonitor`, `EmailChannelAdapter` (a real
  `ProtocolAdapter`, Phase 4; ADAPTER READY / REQUIRES EXTERNAL
  CREDENTIALS), and `ExecutiveRuntime` composing all of them
- ✅ 119 tests: unit, contract, integration (delegation through a real
  `Orchestrator`), 13 adversarial tests (prompt injection, hostile
  tool responses, unauthorized capability requests, duplicate events,
  memory corruption attempts, restart-during-execution proven via a
  real `FileMemoryPolicy` cross-instance recovery, approval expiration,
  contradictory instructions), and one deterministic end-to-end
  fixture matching the Phase 16 directive's own worked scenario
- ✅ A real, runnable, narrated end-to-end demonstration
  (`layla/examples/end_to_end_scenario.py`) against the actual
  `research-intelligence` Chief Domain Agent (Phase 13) — not a fixture
  stand-in — reaching `COMPLETED` through all nine lifecycle states
- ✅ Two real bugs caught by running tests, not asserted away: a
  whole-word-vs-substring matching bug in `CapabilityResolver` ("ai"
  false-matching inside "domain") and a `MockProvider.models` private-
  attribute access in the Final Integration script (Phase 15,
  discovered while wiring Layla's own example)
- ✅ ADR-0020 records the architectural home decision and every reuse
  boundary; `CONTRACT.md` and `README.md` (Framework template +
  Configuration/Lifecycle/Permission/Approval/Memory/Tool policy/
  Deployment/Development/Testing/Troubleshooting/Security sections,
  each honestly marked IMPLEMENTED / PARTIALLY IMPLEMENTED / ADAPTER
  READY / REQUIRES EXTERNAL CREDENTIALS / FUTURE)

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

## Phase 17 — Hardening & Production Readiness — ✅ COMPLETE (2026-08-11)

Post-Phase-16 hardening against the forensic audit's own findings.
Five priorities, worked sequentially; each gets its own ADR (where
architecturally significant), tests, docs, and commit.

- ✅ **17.1 Authentication & Identity** (ADR-0021) — `Principal`/
  `Role`/`Session`/`AuthorizationManager` (`layla/python/avishkar_layla/
  identity.py`, `auth.py`). Fully additive: `ExecutiveRuntime`/
  `ApprovalManager`/`DelegationEngine` accept `authorization=` as an
  *optional* argument — omitted, all 119 Phase 16 tests behave
  unchanged; supplied, every request is authenticated, risk-tier and
  capability permissions are enforced before delegation, self-approval
  is always denied, and an agent-kind `Principal` can structurally
  never hold high-risk or approval authority (checked against actual
  permissions at session-issuance time, not role naming). 30 new
  tests (149 total for Layla).
- ✅ **17.2 Idempotency & Side-Effect Safety** (ADR-0022) —
  `execution.classify_operation()` (READ/WRITE/HIGH_RISK, fail-closed
  default) and `ExecutionTracker` (`layla/python/avishkar_layla/
  execution.py`), persisted through the same `LaylaMemoryPolicy` every
  other Layla component uses. Fully additive: `DelegationEngine`/
  `ExecutiveRuntime` accept `execution_tracker=` as an *optional*
  argument — omitted, all 149 prior tests behave unchanged; supplied,
  a completed delegation never re-invokes the orchestrator on retry, an
  in-flight or uncertain non-READ operation refuses a
  concurrent/crash-recovered retry (proven via a real cross-instance
  `FileMemoryPolicy` recovery test), and a timeout on a non-READ step
  lands on a real, non-terminal `UNKNOWN` state that only an explicit
  `resolve_unknown()` can clear. 21 new tests (170 total for Layla).
- ✅ **17.3 Durable Execution & Resume-in-Place** (ADR-0023) —
  `ExecutiveRuntime.resume(task_id)` reloads a persisted task and
  continues it from exactly its last checkpoint, via one shared,
  state-guarded pipeline (`_advance()`) that `handle_event()` also
  drives — not a second workflow engine. `LaylaTask` gains persisted
  `plan`/`pending_approval_id` fields; `ApprovalManager` gains an
  optional `memory=` for cross-restart durability. Delegation-loop
  resume composes directly with 17.2's `ExecutionTracker` (an already-
  COMPLETED step is never re-run), which is the actual mechanism behind
  the directive's own "50-company task crashes after company 17, resume
  from company 18" example — proven at runnable scale in
  `layla/examples/crash_recovery_scenario.py` (5 steps, crash after 3).
  Found and fixed a real, previously-latent bug in the process:
  `DelegationEngine`'s own per-step approval re-check, redundant with
  `ExecutiveRuntime`'s task-level gate, could wrongly deny a resumed,
  already-granted delegation. 8 new tests (178 total for Layla).
- ✅ **17.4 Concurrency & Event System Hardening** (ADR-0024) —
  audited `EventBus`/`Scheduler`/`ExecutiveRuntime`/`DelegationEngine`/
  Agent Framework/Memory/`ToolRuntime` by reading actual mutation
  patterns; found and fixed real races in `ExecutionTracker.begin()`
  (a check-then-act race undermining Priority 17.2's own idempotency
  guarantee), `ApprovalManager`, `SessionManager`, `AuditLogger`,
  `Scheduler`, and — as a narrow, directive-authorized exception to
  three otherwise-locked frameworks — `core`'s `EventBus`,
  `memory-factory`'s `FileMemoryPolicy` (a real silent-data-loss bug)/
  `SQLiteMemoryPolicy` (previously unusable cross-thread at all), and
  `mcp-factory`'s `MetricsCollector`. Found `Orchestrator`/
  `ChiefDomainAgent`/`InMemoryMemoryPolicy` already safe and left them
  untouched. One lock per component instance (not per-key), never held
  across external work (an orchestrator call, a scheduled callback);
  `ExecutiveRuntime` additionally gets one lock per task id spanning
  `resume()`'s reload-and-advance so racing resumes can't each work off
  a stale snapshot. 11 new tests (`test_concurrency.py`, real
  `threading.Thread`s) — 189 total for Layla; all three touched
  external frameworks' own full suites still pass unmodified (core
  47/47, memory-factory 24/24, mcp-factory 70/70).
- ✅ **17.5 Controlled Live Integration Validation** (ADR-0025) — one
  new, env-gated test
  (`layla/python/tests/test_live_anthropic_integration.py`,
  `@unittest.skipUnless(LIVE_TEST_MODE=1 and ANTHROPIC_API_KEY)`)
  validates the full `ExecutiveRuntime` → `Planner` → `DelegationEngine`
  → a real `ChiefDomainAgent` → real `Router` → real `AnthropicProvider`
  → live Anthropic API → `ResultValidator` → `ExecutiveSynthesizer`
  path — fixed to the cheapest model, `max_tokens=32`, one trivial
  read-only LOW-risk prompt, and an asserted `$0.01` cost ceiling.
  `avishkar_router`'s `CompletionResponse`/`ProviderResponse` gained an
  additive `request_id` field; Layla's `DelegationRecord` gained an
  additive `cost_usd` field. **Credentials were not available when this
  was built — the skip path was verified; a real live run against the
  API was not performed, stated plainly, not fabricated** (see
  `docs/live-integration-guide.md`). 1 new test (190 total for Layla,
  189 passing + 1 skipped by default); router's own 42 tests still pass
  unmodified.

**Phase 17 complete**: all five priorities locked, 732 platform tests
(731 passing + 1 deliberately skipped by design), zero regressions,
two real previously-latent bugs found and fixed by actually running
scenarios end-to-end, one documented and bounded exception to three
otherwise-locked frameworks. See `docs/production-readiness.md` for
the honest production-readiness gate and
`docs/phase17-forensic-report.md` for the full forensic accounting —
neither claims more than what was actually run and observed.

## Mission Layla 1 — Foundation tier (ADR-0026, 2026-08-12)

A six-agent, read-only forensic audit of an external personal-AI
codebase ("GENESIS") plus OpenClaw/Hermes-style architectural targets
preceded any implementation — recorded in full at
`docs/mission-layla-1-plan.md`, including a headline finding that
GENESIS's own safety governor never actually gates its riskiest tool
calls (a tool-naming mismatch) and that real, specific PII is hardcoded
in its source with zero access control. Per that plan's own
recommendation, zero GENESIS code or data was ported; two new Layla
capabilities were built fresh against Avishkar's own contracts,
informed only by the *patterns* worth reusing:

- ✅ **PersonalModel** (Mission Layla Part 1) — Layla's continuously-
  evolving model of the person she works for: identity, preferences,
  goals, decision patterns, work patterns, communication style,
  project context, relationships, behavioral patterns, personal
  knowledge, life events, habits, long-term objectives. Namespaced
  keys inside the same `LaylaMemoryPolicy` every other Layla component
  uses — not a second memory system. Real, enforced contradiction
  handling (`set()` refuses to silently overwrite a different value;
  `correct()` is the explicit, reasoned-overwrite path) and a
  sensitive-category confirmation gate (`relationships`/
  `behavioral_patterns` require `confirmed=True`) — no seed/default
  personal data ships with the module, a deliberate structural
  difference from GENESIS's hardcoded-PII pattern.
- ✅ **ProactiveEngine** (Mission Layla Parts 2 and 11) — answers
  "should Layla act without being asked," which in this architecture
  is also what drives Layla's persistent-runtime SLEEP → EVENT → WAKE
  → ... → SLEEP cycle: a `Scheduler`/`run_forever()` tick is the
  EVENT, `evaluate()` is WAKE+CONTEXT+DECIDE, an `ACT`-level trigger
  always drives the *full* `handle_event()` pipeline (never a
  risk/approval bypass) and fails closed if `authorization` is wired
  with no session supplied for Layla's own use. Two built-in,
  evidence-only evaluators (stuck `REQUIRES_HUMAN` tasks; repeated
  delegation failures) deliberately never reach `ACT` — only a
  caller-supplied evaluator can, by design.
- Both are fully additive (`personal_model=None`, `enable_proactive=
  False` by default) — all 190 prior Layla tests pass unmodified.
  30 new tests (220 total for Layla). One new runnable example,
  `layla/examples/personal_model_and_proactive_scenario.py`.
- Everything outside this scope (Voice, Vision, Computer Control, IoT,
  Knowledge Graph, Skills/Learning, external Channels, Self-improvement)
  is explicitly deferred with a stated reason in
  `docs/mission-layla-1-plan.md` §22, not silently dropped.

## Mission Layla continuation — Parts 3–27 (ADR-0027, 2026-08-16)

Continued autonomously through the full remaining dependency order per
explicit direction, same discipline: implement → test → verify →
integrate → regression → commit, per component, never batched into an
unverified pile.

**Real, fully-working** (zero fabricated output, zero duplicated
abstractions): `PredictionEngine` (Part 3 — real evidence-based
confidence, never hardcoded), `SkillRegistry` (Part 12 — real
`avishkar_evaluation`-gated approval lifecycle), `LearningLoop` (Part
13 — real pattern extraction, never self-approves), `LifeOS` (Part 4 —
extends `PersonalModel`'s own categories/gates, not a competing
structure), `LaylaKnowledgeGraph` (Part 5 — real BFS/shortest-path
graph engine, zero seed data), `WhatsAppChannelAdapter` (Part 9 — a
second real `ProtocolAdapter`, `UniversalToolRegistry` remains the one
router), `BusinessIntelligenceEngine` (Part 26 — real cost/success-rate
aggregation; found and fixed a real gap where delegation audit records
never carried `cost_usd`), `ExecutiveDashboard` (Parts 23/27 — a real
aggregator, not a new cognitive layer). Parts 24/25 (Multi-Agent
Supervision/Project Management) already satisfied by existing
`Orchestrator`/`DelegationEngine`/`Planner`/`ProjectStore` — not
rebuilt.

**Contract/integration-boundary only** (Parts 6–8, 15–17, 21 — Voice,
Vision, OCR, Spatial Intelligence, Environmental Awareness, Browser/
Computer Control, Application Control, Android/ADB, IoT, Sensors,
Robotics, Home Assistant, MQTT): `PerceptionEngine` and
`EmbodimentController` — real, tested contracts with zero hardware/
network/OS-level backend wired, per the mission directive's own
explicit fallback for capabilities that cannot be safely fully
implemented in this pass. `EmbodimentController.request()`'s risk/
approval gate is structural (computed from real text, enforced before
any executor lookup), not name-matched — deliberately closing the
exact bug class (a tool-naming mismatch silently disabling a safety
gate) this mission's own forensic audit found in the external codebase
it studied.

82 new tests — 299 total for Layla, zero regressions at every commit.
Full detail: CONTRACT.md §21–30, DECISIONS.md ADR-0027,
`docs/mission-layla-1-plan.md`.

## Mission Layla Directive D, Part I — Voice (ADR-0028, 2026-08-16)

Directive D escalates past Part 3–27's "contract-only is an acceptable
fallback": real executors and adapters, wherever the environment
genuinely supports them. Recon on this machine (real microphones,
real speakers, a paired Bluetooth headset, working local STT/TTS
packages) found Voice was genuinely buildable for real.

**Real, fully-working**: `EnergyVAD` (adaptive-noise-floor RMS VAD,
`calibrate()` for loud rooms), `FasterWhisperSTT` (real local
CTranslate2 Whisper — a genuine synthesize-then-transcribe round trip
runs automatically), `Pyttsx3TTS` (real local SAPI5 synthesis),
`list_input_devices`/`list_output_devices` (real hardware enumeration,
found this machine's five real input and output devices), `VoiceSession`
(real segmentation/routing/response-synthesis/interruption logic — and
never calls a tool/executor/capability directly; every non-stop-phrase
transcript is routed through the unchanged `ExecutiveRuntime.handle_event()`).

**Real code / ADAPTER READY**: `OpenAIWhisperAPISTT`,
`OpenAITTSProvider` (real HTTP clients, no `OPENAI_API_KEY` configured
in this environment). `MicrophoneFrameSource`/`SpeakerSink` (real,
hardware-backed — construction-validated against this machine's actual
devices, but a live session is never opened non-interactively by the
automated test suite; requires a real deployment to run end to end).

**Not built**: full-duplex acoustic barge-in (detecting speech while
Layla is speaking); only explicit stop-phrase / external
`request_stop()` interruption.

40 new tests — 339 total for Layla, zero regressions at every commit.
Full detail: CONTRACT.md §31, DECISIONS.md ADR-0028, README.md Voice
section.

## Mission Layla Directive D, Part II — Vision/OCR/Spatial Intelligence (ADR-0029, 2026-08-16)

Recon found `Pillow`/`opencv-python`/`pytesseract` already installed
but no real `tesseract` binary — `winget install
UB-Mannheim.TesseractOCR` succeeded during this pass, so OCR could be
built genuinely GREEN instead of settling for ADAPTER READY.

**Real, fully-working**: `extract_text()` (real Tesseract inference,
real per-word boxes/confidence, verified against a synthetically
rendered test image), `detect_template()` (real `cv2.matchTemplate`
classical CV — found and documented a real flat-region false-positive
caveat via its own test suite), `relative_position`/`distance`/
`nearest`/`overlaps`/`iou` (real, dependency-free geometry),
`screen_capture_source`/`screen_ocr_source` (real wiring into the
existing `PerceptionEngine` contract).

**Real code, hardware-backed, not exercised live automatically**:
`capture_screen()` — confirmed working against this machine's real
1366×768 display, but never called against the live screen by the
automated suite (same consent boundary as the microphone).

**Not built**: general-purpose visual/scene classification (no model
bundled or fabricated) and multi-observation perception fusion beyond
the structured fields `PerceptionObservation` already carries.

28 new tests — 367 total for Layla, zero regressions at every commit.
Full detail: CONTRACT.md §32, DECISIONS.md ADR-0029, README.md Vision
section.

## Mission Layla Directive D, Part III — Computer Control (ADR-0030, 2026-08-16)

Real executors registered into the existing, unmodified
`EmbodimentController` gate (ADR-0027) — capability resolution → risk
classification → approval → execution → observation, with no
weakening of that chain.

**Real, fully-working**: `BrowserExecutor` (real headless Chromium via
Playwright — genuinely drives a persistent browser session across
navigate/click/type/get_text/screenshot calls; tested end to end
through the real `EmbodimentController` approval gate), shell execution
and file operations in `ComputerControlExecutor` (real
`subprocess.run` with a fail-closed allowlist; real, path-traversal-
guarded file I/O confined to a workspace root).

**Real code, hardware-backed, not exercised live automatically**: GUI
control (mouse/keyboard/clipboard/screenshot) in
`ComputerControlExecutor` — real `pyautogui`/`pyperclip`, never
invoked against this machine's actual cursor/keyboard by the
automated suite (same consent boundary as the microphone/screen).

**Security finding**: `EMBODIMENT_BROWSER` isn't in
`_DEFAULT_HIGH_RISK_CAPABILITIES`, so plain navigation is LOW risk and
auto-completes — confirmed by a real test both ways, documented as a
deployment-time choice rather than a bug.

**Not built**: application launching, window management (Part III's
remaining named scope) — `psutil`/`pygetwindow` confirmed available
but not wired to `EmbodimentController` this pass.

34 new tests — 401 total for Layla, zero regressions at every commit.
Full detail: CONTRACT.md §34, DECISIONS.md ADR-0030, README.md
Computer Control section.

## Mission Layla Directive D, Part IV — Android/ADB (ADR-0031, 2026-08-16)

No `adb` binary or Android device exists on this development machine
— the honest, Directive-D-sanctioned outcome: real `ADBExecutor` code
(every action builds a real `adb` command line), a real
`is_adb_available()` check (confirmed `False` here, not asserted
either way without checking), dispatch logic fully tested via an
injected `_run` seam, and a real confirmed `ADBNotAvailableError`
("ADAPTER READY") when the genuine `subprocess`-backed path runs on
this machine. Registered for `EMBODIMENT_ADB` (already forced
HIGH-risk by embodiment.py), plus its own dedicated `shell` allowlist
— two independent, non-redundant gates, directly answering Directive
D's "never expose unrestricted ADB execution directly to model
output."

13 new tests — 414 total for Layla, zero regressions at every commit.
Full detail: CONTRACT.md §35, DECISIONS.md ADR-0031.

## Mission Layla Directive D, Part V — Real Communication Channels (ADR-0032, 2026-08-16)

Real transport implementations for six channels, all routed through
the existing `UniversalToolRegistry` — no second router, no new
send-approval mechanism (the existing `classify_risk()`/
`ApprovalManager` gate already covers every channel call).

**Real, fully-working, genuinely verified**: `SMTPEmailTransport`
(real SMTP wire protocol, proven against a real local test server this
suite runs itself), `WhatsAppCloudAPITransport`/
`TelegramBotAPITransport`/`SlackWebAPITransport`/
`DiscordBotAPITransport`/`TwilioSMSTransport` (real HTTP/SDK clients,
each proven via a real network call to the provider's actual API with
a deliberately invalid credential, confirming a real rejection —
zero side effects). Two new full channel adapters beyond
Telegram/Slack/Discord/SMS routing (`TelegramChannelAdapter`,
`SlackChannelAdapter`, `DiscordChannelAdapter`, `SMSChannelAdapter`)
mirror the existing Email/WhatsApp pattern exactly.

**Not built**: LinkedIn, Google services (Gmail/Calendar), Zoom —
Part V's remaining named channels, explicitly deferred rather than
rushed.

29 new tests — 443 total for Layla, zero regressions at every commit.
Full detail: CONTRACT.md §36, DECISIONS.md ADR-0032, README.md
Communication Channels section.

## Mission Layla Directive D, Part VI — Environmental Awareness (ADR-0033, 2026-08-16)

Sensor → Event → EventBus → Perception/Context → Layla → Decision,
built entirely on existing, unmodified `avishkar_core.EventBus` and
`Scheduler` — no new event system, no LLM polling loop.

**Real, fully-working**: `IdleTimeSensor`/`BatterySensor`/
`SystemLoadSensor` (real local OS/process state — this machine
genuinely has a battery, verified for real), `NetworkConnectivitySensor`
(a real socket-level reachability probe), `SensorMonitor` (real
threshold/change-detection — verified that unchanged readings never
flood the EventBus), `EnvironmentalEventBuffer`/
`EnvironmentalChangeEvaluator` (real EventBus filtering + a real,
retry-storm-safe `ProactiveEngine` evaluator, capped at
`ACTION_OBSERVE`). A full end-to-end integration test proves every
piece composes, from a sensor change to a real `ProactiveTrigger`,
with zero LLM calls in the path.

20 new tests — 463 total for Layla, zero regressions at every commit.
Full detail: CONTRACT.md §38, DECISIONS.md ADR-0033, README.md
Environmental Awareness section.

## Mission Layla Directive D, Part VII — Home Assistant (ADR-0034, 2026-08-16)

No live Home Assistant instance exists in this environment — the
honest, Directive-D-sanctioned outcome: real `HomeAssistantExecutor`
REST API client code, verified against a real, minimal, in-repo HTTP
server fixture this suite runs itself (real Bearer-token checking,
real 401 handling), registered for `EMBODIMENT_HOME_ASSISTANT`
(already forced HIGH-risk by embodiment.py) with no change to that
existing gate. A real end-to-end test proves an approved `list_states`
call reaches the fixture server and a denied `call_service` call never
does.

One real, disclosed environmental finding: a Playwright click test
flaked once under heavy real CPU contention from this actively-used
development machine's own concurrent browser usage (21+ real
`chrome.exe` processes observed), independently confirmed to pass
cleanly in isolation — a property of the test environment, not a code
defect, and not papered over by loosening a production timeout.

11 new tests — 474 total for Layla, zero regressions (confirmed) at
every commit. Full detail: CONTRACT.md §40, DECISIONS.md ADR-0034,
README.md Home Assistant section.

## Mission Layla Directive D, Part VIII — MQTT (ADR-0035, 2026-08-16)

A real, minimal, in-repo MQTT 3.1.1 broker (`tests/_minimal_mqtt_broker.py`)
was built specifically to reach real GREEN status rather than settle
for ADAPTER READY — `test.mosquitto.org` was confirmed unreachable
from this sandboxed environment, but MQTT's protocol is fully
specifiable and testable without any external dependency.

**Real, fully-working**: `MQTTBridge` (real `paho-mqtt`, real connect/
auth/publish/subscribe/reconnect, real EventBus event translation for
every inbound message), real fail-closed topic allowlists with real
MQTT `+`/`#` wildcard matching, a full real end-to-end test (publish →
real broker → real `on_message` → real `EventBus` event).

**Real bug found and fixed by this pass's own first test run**:
`paho-mqtt` 2.x's VERSION2 callback API passes a real `ReasonCode`
object to `on_connect`, not a plain int — `int(reason_code)` raised a
real `TypeError`, fixed via the library's own `is_failure` property.

**Real security enhancement**: `EMBODIMENT_MQTT` added to
embodiment.py's `_DEFAULT_HIGH_RISK_CAPABILITIES` — an MQTT publish
routinely commands real physical devices, the same reasoning already
applied to Home Assistant/ADB/Computer Control/Robotics. A strictly
conservative change (gates more, never less), confirmed safe by
grepping the whole tree first.

17 new tests — 491 total for Layla, zero regressions. Full detail:
CONTRACT.md §42, DECISIONS.md ADR-0035, README.md MQTT section.

## Mission Layla Directive D, Part IX — Robotics/Embodiment (ADR-0036, 2026-08-16)

Built entirely on existing components (`EmbodimentController`,
`risk.classify_risk`, `ApprovalManager`, `AuditLogger`) — no new
cognitive/risk/event framework. No physical robot exists in this
environment, and unlike MQTT there's no single standard "robot
protocol" a local fixture could faithfully stand in for — the honest
scope this pass covers is the platform-independent safety logic
Directive D explicitly requires, genuinely real and tested without any
hardware via an injected fake driver.

**Real, fully-working**: `RobotSafetyController` — a real emergency-
stop latch (engages even if the real driver's own stop call fails), a
real human-override check ahead of even an already-granted approval, a
real enforced timeout/cancellation via `Thread.join()`, real fail-safe
triggering on any timeout or driver exception (which itself also
latches the emergency stop until an explicit, human-attributed
reset), real state verification, and a real audit trail. 3 real
end-to-end tests through the unmodified `EmbodimentController` gate.

**Adapter ready**: physical robot hardware itself — `RobotDriver` is
the documented boundary a deployment implements for its real platform.

14 new tests — 505 total for Layla, zero regressions. Full detail:
CONTRACT.md §44, DECISIONS.md ADR-0036, README.md Robotics section.

## Mission Layla Directive D, Part X — Personal Executive Communication (ADR-0037, 2026-08-16)

Implements Directive D's own worked example exactly: "Avishkar has not
responded to this person for 7 days → … → Generate draft → Risk
assessment → Approval policy → Send → Record outcome → Update memory."
Calendar/Meetings/Appointments/Reminders are already real, existing
`LifeOS` functionality — not rebuilt.

**Real, fully-working**: `StaleRelationshipEvaluator` (real
relationship lookup, real staleness computation, real eligibility
filtering, real retry-storm-safe dedup, emits `ACTION_SUGGEST` only —
never autonomous send), `record_contact_outcome()` (a real, provenance-
tracked `PersonalModel` update). A full real `ProactiveEngine`
integration test proves the chain composes end to end.

**Deliberately not reimplemented**: draft generation, risk
classification, approval, and sending — these are exactly what the
unchanged `ExecutiveRuntime.handle_event()` pipeline already does;
duplicating them here would violate "Avishkar OS remains the
foundation."

11 new tests — 516 total for Layla, zero regressions. Full detail:
CONTRACT.md §46, DECISIONS.md ADR-0037, README.md Personal Executive
Communication section.

## Mission Layla Directive D, Part XI — 24/7 Operation (ADR-0038, 2026-08-16)

Real hardening of the existing `Scheduler`/`ExecutiveRuntime.run_forever()`
loop — no new persistent-runtime mechanism.

**Real bug found and fixed** (not just a feature added): `Scheduler.tick()`
called a job's callback with no exception handling at all — one
failing recurring job could crash the entire 24/7 loop. Now
unconditionally isolated.

**Real, fully-working**: optional dead-letter escalation
(`max_consecutive_failures`, a real `cancel()` after repeated
failures), real graceful shutdown (`request_shutdown()`, a real
`threading.Event`), real heartbeat/liveness (`last_tick_at`/
`is_alive()`, using the runtime's own injectable clock), real
start/stop audit records, and a real `operational_health()`
aggregation (liveness, incomplete-task count, scheduler pending/dead-
letter state).

21 new tests — 537 total for Layla, zero regressions. Full detail:
CONTRACT.md §48, DECISIONS.md ADR-0038, README.md 24/7 Operation
section.

## Mission Layla Directive D, Part XII — Durable Execution (ADR-0039, 2026-08-16)

Most of "durable execution" was already real (checkpoints/resume-in-
place, idempotency keys, retry policies, an execution journal) — not
rebuilt. `TaskLeaseManager` adds the two items nothing existing
covered: task ownership and stale-task recovery.

**Real, fully-working**: thread-safe, durable `acquire()`/`renew()`/
`release()`/`is_stale()`/`find_stale_leases()`, with a genuine 20-real-
thread concurrency test proving exactly one wins a contested lease.

**Explicitly, honestly scoped**: NOT a distributed lock service — true
multi-process atomicity depends on the underlying memory backend's own
guarantees, which this layer doesn't provide. Correctly scoped for
Directive D's own actual framing ("a machine restart must not destroy
a task"), not oversold.

14 new tests — 551 total for Layla, zero regressions. Full detail:
CONTRACT.md §50, DECISIONS.md ADR-0039, README.md Durable Execution
section.

## Mission Layla Directive D, Part XIII — Security Hardening (ADR-0040, 2026-08-16)

A fresh security review across authentication/authorization/secrets/
injection/exfiltration/SSRF. Most of Directive D's list was already
real, existing coverage from earlier phases; this pass's real job was
finding what wasn't covered yet.

**Real finding, fixed** (not merely documented as a gap): `EMBODIMENT_BROWSER`
is LOW-risk-by-default for harmless-*sounding* text (ADR-0030) — a
`navigate` to a cloud metadata endpoint
(`http://169.254.169.254/latest/meta-data/iam/security-credentials/`)
previously reached Playwright with zero approval gate, a genuine real-
world SSRF-to-credential-theft pattern. Fixed with a real, hard block
(`ssrf_guard.py`) refusing navigation to private/loopback/link-local/
reserved addresses and known metadata hostnames, verified end to end
against the real `BrowserExecutor`.

**Clean sweep**: a repository-wide secret scan found only pre-existing,
known test fixtures — zero real secrets, zero new findings across all
of Parts I–XIII.

11 new tests — 562 total for Layla, zero regressions. Full detail:
CONTRACT.md §52, DECISIONS.md ADR-0040, README.md Security Hardening
section.

## How this roadmap changes

A phase only moves to 🚧 when someone is actively working it, and only to
✅ when its module's README (per STANDARDS.md's template) is accurate and
its Limitations section is honest. Reordering phases or adding a new
factory requires an ADR in [DECISIONS.md](./DECISIONS.md) first.
