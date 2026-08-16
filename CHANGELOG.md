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
- **ROADMAP.md restructured**: the original combined "Phase 8 — Prompt +
  Template + Starter Kit" split into individual Phases 8/9/10, and
  Phases 11–15 (Evaluation, Security, remaining 10 Chief Domain Agents,
  Knowledge Library, Final Integration) added explicitly, matching the
  Execution Mode phase list (ADR-0012). `evaluation-factory` and
  `security-factory` moved out of the "Deferred" list since they're now
  scheduled at Phases 11/12.
- **ADR-0014**: `prompt-factory` ships its own `Scorer` seam rather than
  depending on the not-yet-built `evaluation-factory` (Phase 11); no new
  agent-factory bridge needed since a rendered prompt is already a `str`.
- **Prompt Framework — Phase 8 locked**: `avishkar_prompt` —
  `PromptVersion` (validated at construction: every template
  placeholder must be declared), `render()`, `PromptRegistry`
  (versioned, immutable-once-registered), plus a scoring seam
  (`exact_match_scorer`, `keyword_presence_scorer`, `evaluate_version`,
  `compare_versions`) forward-compatible with Phase 11. 24 tests, a
  runnable example evaluating two prompt versions and feeding the
  winner into a real `ChiefDomainAgent`.
- **ADR-0015**: `template-factory` wraps `avishkar_prompt.PromptVersion`
  directly (as a field of `TemplateFile`) instead of redefining a
  parallel validated-string type.
- **Template Framework — Phase 9 locked**: `avishkar_template` —
  `TemplateFile`/`Template`/`TemplateRegistry`, `instantiate()` (writes
  a template to a real target directory, all-or-nothing on collision,
  never overwrites without `overwrite=True`), and
  `MODULE_README_TEMPLATE` formalizing STANDARDS.md §2.1 as a real,
  instantiable template. 15 tests, a runnable example instantiating
  both the built-in template and a custom project skeleton.
- **ADR-0016**: `starter-kit-factory` ships one generic kit rather than
  a named-product kit ("no business logic in the platform"); a
  `StarterKit` composes portable data with generated source code, not
  serialized runtime objects.
- **Starter Kit Framework — Phase 10 locked**: `avishkar_starter_kit` —
  `StarterKit`/`StarterKitRegistry`/`materialize()`, and
  `AGENT_WITH_MEMORY_AND_KNOWLEDGE`, a real kit composing an agent,
  memory, knowledge, and a workflow. 12 tests, a runnable example that
  materializes the kit and actually runs its generated `main.py` as a
  subprocess (exit 0).
- **ADR-0017**: `evaluation-factory` closes ADR-0014's scoring seam as
  a bridge into `agent-factory`'s existing `QualityGate`, not the
  reverse -- `agent-factory`'s locked source stays untouched.
- **Evaluation Framework — Phase 11 locked**: `avishkar_evaluation` —
  `EvalSuite`/`run_suite()`/`passes_threshold()` (reusing
  `EvalCase`/`EvalReport`/`RegressionResult`/`Scorer` from
  `prompt-factory` verbatim), two more scorers
  (`length_bounds_scorer`, `weighted_keyword_scorer`), and two bridges
  (`make_quality_gate()` into `agent-factory`, `evaluate_workflow_result()`
  into `workflow-factory`). 16 tests, a runnable example with a real
  `ChiefDomainAgent` gated by a `QualityGate` this framework built.
- **ADR-0018**: `security-factory` keeps automated secret scanning and
  human-judgment checklist review explicitly separate; guardrails
  bridge into `agent-factory`'s existing `Guardrail` type.
- **Security Framework — Phase 12 locked**: `avishkar_security` —
  `scan_for_secrets`/`redact_secrets`/`scan_repository_for_secrets`
  (real, automated), `SECURITY_CHECKLIST`/`run_checklist()` (structured
  self-assessment), and three real guardrail bridges
  (`make_secret_scanning_guardrail`, `make_rate_limit_guardrail`,
  `make_input_validation_guardrail`). 24 tests. The example actually
  ran a retroactive secret scan across the whole repository: zero real
  findings.
- **Phase 13 in progress**: remaining 10 Chief Domain Agents, each to
  the 30-section template, each wiring at least one real Phase 5–12
  framework. **Medical & Healthcare** landed first: real
  `SQLiteMemoryPolicy`, a real `KnowledgeBase` (clinical guidelines),
  a `make_quality_gate()`-built quality gate, and
  `make_secret_scanning_guardrail()` reused from `security-factory`.
  16 tests, a runnable example.
- **Legal & Compliance** landed second: real `FileMemoryPolicy` (a
  different backend than Medical & Healthcare's SQLite -- cross-instance
  persistence verified by test and example), a real `KnowledgeBase`
  (NDA basics, contract-review checklist), the same evaluation/security
  bridges. 15 tests, a runnable example.
- **Startup, Business & Product** landed third: real `SQLiteMemoryPolicy`,
  a real `KnowledgeBase` (PRD structure, pitch-deck checklist),
  pitch-clarity and market-size-classification tools. 13 tests, a
  runnable example.
- **Education & Knowledge** landed fourth: real `FileMemoryPolicy`, a
  real `KnowledgeBase` (curriculum design, Bloom's taxonomy),
  reading-level and learning-objective-format tools. 13 tests, a
  runnable example.
- **Research & Intelligence** landed fifth: real `SQLiteMemoryPolicy`,
  a real `KnowledgeBase` (scientific method, source evaluation),
  source-reliability and confidence-level tools. 14 tests, a runnable
  example.
- **Finance & Economics** landed sixth: real `FileMemoryPolicy`, a
  real `KnowledgeBase` (financial ratios, risk assessment), and
  `make_rate_limit_guardrail()` -- a different `security-factory`
  bridge than prior agents, proving it's genuinely reusable, with a
  real integration test proving the 11th call within a window blocks.
  14 tests, a runnable example.
- **Government & Public Policy** landed seventh: real
  `SQLiteMemoryPolicy`, a real `KnowledgeBase` (policy-analysis
  framework, public-comment process), policy-structure and
  regulatory-scope tools. 14 tests, a runnable example.
- **Human Development & Psychology** landed eighth: real
  `FileMemoryPolicy`, a real `KnowledgeBase` (active listening, growth
  mindset), and this repository's most safety-critical guardrail --
  `crisis-escalation`, whose block reason carries real crisis-resource
  contact information (the 988 Suicide & Crisis Lifeline), not just a
  refusal, verified by test that `"988"` literally appears in the
  returned `blocked_reason`. 12 tests, a runnable example.
- **Creative & Media** landed ninth: real `SQLiteMemoryPolicy`, a real
  `KnowledgeBase` (story structure, copy editing), word-count and
  pacing-analysis tools -- the pacing test caught and fixed a real
  fixture-arithmetic bug (a "26-word" sentence that was actually 19
  words). 14 tests, a runnable example.
- **Orchestrator landed tenth, completing Phase 13**: no `blueprint.json`
  by design -- it composes the real `avishkar_agent.Orchestrator`
  (Phase 3) over live instances of all 10 domain agents rather than
  reasoning itself. `build_all_domain_agents()` builds all 10 for real;
  `build_executive_orchestrator()` wires them into one Orchestrator.
  7 tests, including one proving every one of the 10 agents actually
  completes a real task (not just constructs). A runnable example
  demonstrates `route()`/`delegate_team()`/`broadcast()`/
  `resolve_conflict()` against real dispatched results -- the whole
  platform, composed and running. **All 11 ADR-0007 roster seats are
  now real, tested, documented Chief Domain Agents.**
- **Phase 14 (Knowledge Library) locked**: three concrete, product-
  facing shelf artifacts, one per shelf directory that previously held
  only a README pointing at its owning factory:
  - `knowledge/platform-standards/` — a real `KnowledgeBase` seeded
    with genuine `STANDARDS.md` excerpts. 4 tests, a runnable example.
  - `workflows/cross-domain-review/` — a real, reusable two-agent
    `WorkflowSpec`, demonstrated with `legal-compliance` +
    `finance-economics`. 3 tests, a runnable example.
  - `templates/framework-readme/` — formalizes STANDARDS.md §2.2's
    Framework template as a real `Template`. 2 tests, a runnable
    example.
  No duplicate checklist built -- `security-factory`'s
  `SECURITY_CHECKLIST` (Phase 12) already fills that role.
- **ADR-0019**: Execution Mode (ADR-0012) closed. Final metrics: 542
  tests passing platform-wide (382 across 16 factories/frameworks, 9
  across Phase 14's three Knowledge Library modules, 151 across all 11
  Chief Domain Agents), zero known regressions.
- **Phase 15 (Final Integration) locked, completing all 15 phases**:
  `docs/final-integration.md` + `docs/final-integration-verify.py` --
  one real, runnable script exercising Core Engine, AI Router,
  Universal Integration, Agent Framework, Memory, Knowledge, Workflow,
  Evaluation, and Security together in a single workflow, with real
  captured output committed. Root `README.md` and `ARCHITECTURE.md`
  §7 Status sections updated from initial-scaffold text to reflect the
  platform's real, complete state.
- **ADR-0020**: Layla is a new top-level platform capability
  (`layla/`), not a Chief Domain Agent or a factory, composed entirely
  from existing frameworks' public contracts — zero parallel systems.
- **Phase 16 (Layla) locked**: `avishkar_layla` — a Personal Executive
  Intelligence layer: `StateMachine`, `LaylaMemoryPolicy` (wraps
  `avishkar_agent.MemoryPolicy`), `ProjectStore`, `IntentInterpreter`,
  `ContextBuilder`, risk classification + `ApprovalManager` (reuses
  `ApprovalGate`), `CapabilityResolver` + `Planner`, `DelegationEngine`
  (wraps `Orchestrator`), `ResultValidator`/`ConflictResolver`
  (reuses `HashingEmbedder`)/`ExecutiveSynthesizer`, `Scheduler`,
  `AuditLogger`/`SessionManager` (durable, restart-safe, proven via a
  real cross-instance `FileMemoryPolicy` recovery test),
  `NotificationManager`/`HealthMonitor`, `EmailChannelAdapter` (a real
  `ProtocolAdapter`; ADAPTER READY / REQUIRES EXTERNAL CREDENTIALS),
  and `ExecutiveRuntime` composing all of them around the directive's
  own IDLE/EVENT/INGEST/UNDERSTAND/DECIDE/PLAN/ACT/VERIFY/SLEEP loop.
  119 tests including 13 adversarial tests and a deterministic
  end-to-end fixture. A real, runnable, narrated demonstration against
  the actual `research-intelligence` Chief Domain Agent reaches
  `COMPLETED` through all nine lifecycle states. Two real bugs caught
  by running tests: a whole-word-vs-substring matching bug in
  `CapabilityResolver`, and a `MockProvider.models` private-attribute
  access surfaced while wiring the example.
- **Forensic audit (`docs/phase16-forensic-audit.md`)**: an evidence-
  based audit of all 16 phases -- a repo-wide grep sweep (zero
  placeholder markers, zero stub functions, zero `NotImplementedError`/
  bare `except:`, zero duplicate abstractions), a real repo-wide secret
  scan (25 matches, 100% traced to well-known-fake test fixtures, zero
  real secrets), a dependency-direction check (`core`/`router` import
  nothing else in the platform), and per-phase production-readiness
  scores. Headline finding (SEC-1, HIGH): no test in this repository
  has ever made a real network call to a live external system --
  every external boundary is tested via dependency injection against
  fakes, which is good test hygiene but means live-provider behavior
  has never been verified. Zero CRITICAL findings. Full list of
  security/reliability/integration/performance/code-quality findings
  and recommended Phase 17+ work in the audit document itself.

- **Phase 17.1 (Authentication & Identity) locked (ADR-0021)**:
  `Principal`/`Role`/`Session`/`AuthorizationManager`
  (`layla/python/avishkar_layla/identity.py`, `auth.py`) -- a minimal,
  additive identity boundary responding directly to the Phase 16
  audit's SEC-3 finding (no auth model existed anywhere in the
  platform). `ExecutiveRuntime`, `ApprovalManager`, and
  `DelegationEngine` all accept `authorization=` as an *optional*
  constructor argument -- omitted, behavior is byte-for-byte Phase 16
  (all 119 original Layla tests pass unmodified); supplied, every
  `handle_event()` call authenticates and requires `PERM_COMMAND`
  before a task exists, checks the session's risk-tier permission
  before even creating an `ApprovalRequest`, enforces
  `Role.allowed_capabilities` against every planned step
  (least-privilege capability enforcement), and `ApprovalManager
  .grant()` requires `PERM_APPROVE` and always denies self-approval.
  An agent-kind `Principal` can structurally never be issued high-risk
  or approval authority -- `AuthorizationManager.issue_session()`
  checks the role's actual permission set, not its name, so even a
  maliciously-renamed custom role is refused. 30 new tests (149 total
  for Layla).

- **Phase 17.2 (Idempotency & Side-Effect Safety) locked (ADR-0022)**:
  `execution.classify_operation()` (READ/WRITE/HIGH_RISK -- a distinct
  axis from `risk.classify_risk`, with a fail-closed default: text
  matching neither a recognized READ nor WRITE/HIGH_RISK verb
  classifies WRITE, never READ) and `ExecutionTracker`
  (`layla/python/avishkar_layla/execution.py`), persisted through the
  same `LaylaMemoryPolicy` every other Layla component already uses --
  no new storage mechanism. `DelegationEngine` and `ExecutiveRuntime`
  both accept `execution_tracker=` as an *optional* constructor
  argument -- omitted, behavior is byte-for-byte Phase 16/17.1 (all 149
  prior Layla tests pass unmodified); supplied, every delegation is
  tracked under an idempotency key of `{task_id}:{plan_step.id}`: a
  completed delegation short-circuits and never re-invokes the real
  `Orchestrator` on a duplicate call; a record still
  AUTHORIZED/APPROVED/EXECUTING/UNKNOWN from a prior attempt that never
  reached a terminal state -- whether a concurrent duplicate call or a
  crash mid-flight, which look identical from the record alone --
  refuses any non-READ retry, fail-closed; a timeout on a non-READ step
  lands on a real, non-terminal UNKNOWN state (deliberately excluded
  from `TERMINAL_EXECUTION_STATES`) rather than FAILED, since FAILED
  would imply "safe to retry" and a timeout does not guarantee that --
  only an explicit `ExecutionTracker.resolve_unknown()` call clears it.
  A new `IdempotencyConflictError` guards against the same key being
  reused for a genuinely different operation. Proven via a real
  cross-instance crash-recovery test: a fresh `ExecutionTracker` in a
  brand-new process, against the same on-disk `FileMemoryPolicy` store
  as a delegation left `EXECUTING` by a simulated crash, correctly
  refuses to blindly re-run it. Does not reach into `mcp-factory`
  (Phase 4, locked) -- idempotency tracking guards the one seam Layla
  owns (`DelegationEngine.delegate()`), not a delegated agent's own
  direct tool calls, per this repository's "later frameworks wrap,
  never modify earlier locked frameworks" discipline. 21 new tests
  (170 total for Layla).

- **Phase 17.3 (Durable Execution & Resume-in-Place) locked
  (ADR-0023)**: `ExecutiveRuntime.resume(task_id, session_id=None)` --
  reloads a persisted `LaylaTask` and continues it from exactly the
  state it was last checkpointed in. `handle_event()` and `resume()`
  are two thin entry points around one shared, state-guarded
  `_advance()` pipeline -- every stage is guarded by the task's current
  `state`, so a reloaded task skips straight to its first unfinished
  stage instead of restarting. Not a second workflow engine: reuses the
  same `StateMachine`/`Planner`/`ApprovalManager`/`DelegationEngine`
  every other path already goes through. `LaylaTask` gains two
  persisted fields -- `plan` (the actual `Plan`, not just `plan_id` --
  a resumed task never re-plans) and `pending_approval_id` (so a task
  left `APPROVAL_PENDING` can have that exact request re-checked).
  `ApprovalManager` gains an optional `memory=` parameter -- omitted,
  behavior unchanged (in-process dict, lost on restart); supplied, as
  `ExecutiveRuntime` always does, every approval request/grant/deny is
  persisted, so a pending or decided approval survives a restart.
  Delegation-loop resume composes directly with Priority 17.2's
  `ExecutionTracker`: a resumed `EXECUTING` task re-runs the full
  delegation loop over its persisted plan, and an already-`COMPLETED`
  step is returned from cache without invoking the orchestrator again
  -- the actual mechanism satisfying the directive's own "a 50-company
  research task crashes after company 17, must resume from company 18"
  example, proven at runnable scale (5 steps, crash after 3, only the 2
  remaining steps re-delegated) in
  `layla/examples/crash_recovery_scenario.py`. A real, previously-
  latent bug was found and fixed in the process: `DelegationEngine`'s
  own per-step approval re-check (a legitimate standalone feature) is
  redundant with `ExecutiveRuntime`'s task-level risk/approval gate,
  and was invisible in Phase 16/17.1 because an ungated pending
  task-level approval never reached `DELEGATING` -- but `resume()` can
  now legitimately carry a task-level-granted approval through to
  `DELEGATING`, where the orphaned per-step request (its id never
  surfaced to any human) would have wrongly denied it; fixed by no
  longer wiring `approval_manager=` into the `DelegationEngine`
  `ExecutiveRuntime` constructs internally. Also fixed: Phase 16/17.1
  always collapsed a genuinely-pending, ungated approval straight to
  `REQUIRES_HUMAN`, since nothing could ever check it again --
  `APPROVAL_PENDING` is now a real, persisted, resumable state, only
  collapsing to `REQUIRES_HUMAN` once actually denied/expired. 8 new
  tests (178 total for Layla).

- **Phase 17.4 (Concurrency & Event System Hardening) locked
  (ADR-0024)**: audited `EventBus`, `Scheduler`, `ExecutiveRuntime`,
  `DelegationEngine`, the Agent Framework, Memory, and `ToolRuntime` by
  reading actual mutation patterns rather than assuming. Found and
  fixed real races: `ExecutionTracker.begin()`'s get-or-create was a
  genuine check-then-act race that could let two concurrent callers
  both create an idempotency record for the same key -- defeating the
  exact guarantee Priority 17.2 exists to provide; closed with a lock
  plus a non-persisted `claimed_this_call` marker on the returned
  record (distinguishing "I created this" from "I observed one already
  there," since both cases share the same `EXEC_REQUESTED` status), and
  `_CLAIMED_NON_TERMINAL_STATES` now includes `EXEC_REQUESTED`.
  `ApprovalManager.grant()`/`deny()`, `SessionManager.save()`'s shared
  index, `AuditLogger.record()`'s shared per-scope sequence number, and
  `Scheduler`'s heap/jobs/callbacks all gained a guarding lock (a
  callback/handler never runs while the lock is held, to avoid blocking
  unrelated operations or deadlocking on re-entrant callbacks).
  `ExecutiveRuntime` gained one lock per task id spanning the *entire*
  `_advance()` call, including `resume()`'s reload -- closing a real gap
  where two racing `resume()` calls on the same task could each work
  off a stale in-memory snapshot and duplicate delegated work. As a
  narrow, directive-authorized exception to three otherwise-locked
  frameworks (justified because Phase 17 explicitly names EventBus/
  Memory/ToolRuntime as audit/harden targets, and because every change
  is additive with zero effect on single-threaded behavior): `core`'s
  `EventBus` gained a lock around `_subscribers`/`_next_id`;
  `memory-factory`'s `FileMemoryPolicy` gained a lock closing a real,
  silent data-loss bug (concurrent `remember()` calls for different
  keys in the same kind file could lose one entirely via a whole-file
  load-mutate-save race) and `SQLiteMemoryPolicy` gained
  `check_same_thread=False` plus a lock (it previously could not be
  used cross-thread *at all*); `mcp-factory`'s `MetricsCollector`
  gained a lock around its counter increments. `Orchestrator`/
  `ChiefDomainAgent`/`InMemoryMemoryPolicy` were audited and found
  already safe (read-only shared state after construction / single
  atomic dict operations, respectively) and left untouched. 11 new
  tests (`test_concurrency.py`, real `threading.Thread`s, a sleep-
  injecting test double plus `threading.Barrier` to deterministically
  widen and hit race windows too narrow for natural GIL scheduling) --
  189 total for Layla, up from 178, zero regressions; all three touched
  external frameworks' own full test suites also still pass unmodified
  (core 47/47, memory-factory 24/24, mcp-factory 70/70).

- **Phase 17.5 (Controlled Live Integration Validation) locked
  (ADR-0025)**: one new, env-gated test
  (`layla/python/tests/test_live_anthropic_integration.py`),
  `@unittest.skipUnless(LIVE_TEST_MODE=1 and a real ANTHROPIC_API_KEY)`
  -- skipped by default, exactly like every other test in this
  platform is offline by default. Validates the full path
  `ExecutiveRuntime.handle_event()` -> `Planner` -> `DelegationEngine`
  -> a real `ChiefDomainAgent` -> a real `avishkar_router.Router` ->
  the real `AnthropicProvider` -> the live Anthropic Messages API ->
  `ResultValidator` -> `ExecutiveSynthesizer`, closing Phase 16's
  headline audit finding (SEC-1: no test in this platform had ever
  made a real network call). Fixed to `claude-haiku-4-5` (cheapest
  catalog model), `max_tokens=32`, one trivial fixed read-only LOW-risk
  prompt, and an explicit `$0.01` cost-ceiling assertion the test fails
  loudly against rather than silently accepting unexpected spend; never
  reaches a write-classified delegation, never triggers an approval
  gate, never invokes a tool/channel adapter -- no email, message,
  financial, or destructive operation anywhere in this test.
  `avishkar_router`'s `CompletionResponse`/`ProviderResponse` gained an
  additive `request_id` field (populated by `AnthropicProvider` from
  the live response's own `.id`; `None` for `MockProvider`), closing
  the one gap in Router's already-real cost/latency/token tracking
  (computed and logged/published since Phase 2). Layla's own
  `DelegationRecord` gained an additive `cost_usd` field, passed
  through from the delegated agent's `AgentResult.cost_usd`.
  **Credentials were not available in the environment this priority
  was built in.** The skip path (missing credentials -> skipped, not
  faked) was verified correct; a real live call against the Anthropic
  API was NOT performed as part of this work -- stated plainly per the
  directive's own explicit instruction not to fabricate successful live
  validation. `docs/live-integration-guide.md` gives exact execution
  instructions for whoever runs it first with a real key. 1 new test
  (190 total for Layla: 189 passing offline + 1 skipped by default);
  router's own 42 tests still pass unmodified.

- **Mission Layla 1 (PersonalModel + ProactiveEngine) locked
  (ADR-0026)**: preceded by a six-agent, read-only forensic audit of an
  external personal-AI codebase ("GENESIS") plus OpenClaw/Hermes-style
  architectural targets, recorded in full at
  `docs/mission-layla-1-plan.md` -- headline findings included GENESIS's
  own safety governor never actually gating its riskiest tool calls (a
  tool-naming mismatch between its hardcoded dangerous-tool list and
  its real tool-registry IDs), `permissions.json` explicitly allowing
  filesystem delete/mouse-keyboard takeover/browser automation by their
  real IDs, an identity-verification check that fails open due to a
  type-mismatch bug, an unconditional command-injection backdoor in its
  voice pipeline, and real, specific PII (names, family members, health
  conditions) hardcoded in plaintext source with zero access control.
  Per that plan's own recommendation, zero GENESIS code or data was
  ported into Avishkar OS -- two new Layla capabilities were built
  fresh against Avishkar's own contracts, informed only by the design
  *patterns* judged worth reusing.

  `PersonalModel` (Mission Layla Part 1,
  `layla/python/avishkar_layla/personal_model.py`) -- Layla's
  continuously-evolving model of the person she works for across 13
  categories (identity, preferences, goals, decision patterns, work
  patterns, communication style, project context, relationships,
  behavioral patterns, personal knowledge, life events, habits,
  long-term objectives), stored as namespaced keys inside the same
  `LaylaMemoryPolicy` every other Layla component already uses -- not a
  second memory system. `set()` refuses to silently overwrite an
  existing, different value (`PersonalFactContradictionError` unless
  `resolve=`/`correct()` is used explicitly); writing the same value
  twice is idempotent. `SENSITIVE_CATEGORIES` (`relationships`,
  `behavioral_patterns`) require `confirmed=True` on every write, and
  `summary()` never includes their content verbatim -- only a category
  name and count. No category ships with seed/default personal data of
  any kind, a deliberate structural difference from GENESIS's
  hardcoded-PII pattern.

  `ProactiveEngine` (Mission Layla Parts 2 and 11,
  `layla/python/avishkar_layla/proactive.py`) -- answers "should Layla
  act without being asked," which in this architecture is also what
  drives Layla's persistent-runtime SLEEP -> EVENT -> WAKE -> ... ->
  SLEEP cycle: a `Scheduler`/`run_forever()` tick is the EVENT,
  `evaluate()` is WAKE+CONTEXT+DECIDE, and an `ACT`-level trigger always
  drives the *full* `handle_event()` pipeline (risk, approval,
  delegation -- everything), never a bypass; fails closed
  (`UnauthenticatedError`, caught and audited) if `authorization` is
  wired and no session was supplied for Layla's own autonomous use. Two
  built-in evaluators, both computed from real `SessionManager`/
  `AuditLogger` state, never fabricated: a task stuck in
  `REQUIRES_HUMAN` past a configurable age escalates SUGGEST ->
  URGENTLY_ALERT; a task with repeated delegation failures escalates
  OBSERVE -> SUGGEST. Neither built-in ever reaches ACT -- genuine
  autonomous behavior requires a caller-supplied evaluator for a
  specific, well-understood scenario, deliberately not invented
  speculatively.

  Both integrations are fully additive
  (`ExecutiveRuntime(personal_model=None, enable_proactive=False)` by
  default) -- all 190 prior Layla tests pass unmodified. One new
  runnable example
  (`layla/examples/personal_model_and_proactive_scenario.py`). 30 new
  tests -- 220 total for Layla, up from 190, zero regressions.
  Everything outside this scope (Voice, Vision, Computer Control, IoT,
  Knowledge Graph, Skills/Learning, external Channels, Self-improvement)
  is explicitly deferred with a stated reason in
  `docs/mission-layla-1-plan.md` SS22, not silently dropped.

- **Mission Layla continuation, Parts 3-27 (ADR-0027)**: continued
  autonomously through the full remaining dependency order, per
  explicit direction, same discipline as every prior priority
  (implement -> test -> verify -> integrate -> regression -> commit,
  per component).

  Real, fully-working: `PredictionEngine` (prediction.py, Part 3 --
  every Prediction carries evidence and a genuinely computed confidence,
  a real ratio/frequency over SessionManager/AuditLogger history, never
  a hardcoded literal); `SkillRegistry` (skills.py, Part 12 -- a real
  CANDIDATE -> EVALUATING -> APPROVED|REJECTED -> RETIRED lifecycle
  gated by avishkar_evaluation's real run_suite()/passes_threshold(),
  directly avoiding the exact bug this mission's forensic audit found
  in the external codebase it studied: a `learned` flag never actually
  set anywhere); `LearningLoop` (learning.py, Part 13 -- real pattern
  extraction over completed-task history proposes SkillRegistry
  candidates, never self-approves, never touches source code);
  `LifeOS` (life_os.py, Part 4 -- a thin layer extending PersonalModel's
  own categories with schedule/tasks/finance/health/travel/
  appointments/reminders, finance/health joining SENSITIVE_CATEGORIES,
  not a competing structure); `LaylaKnowledgeGraph` (knowledge_graph.py,
  Part 5 -- a real, minimal, from-scratch graph engine: typed nodes/
  edges, real BFS/shortest-path, referential integrity enforced, zero
  seed data, additive alongside Avishkar's existing vector-search
  Knowledge Framework); `WhatsAppChannelAdapter` (channels/
  whatsapp_adapter.py, Part 9 -- a second real ProtocolAdapter, the
  exact EmailChannelAdapter ADAPTER READY pattern; UniversalToolRegistry
  remains the one router, no second router built);
  `BusinessIntelligenceEngine` (business_intelligence.py, Part 26 --
  real task/cost/success-rate aggregation over AuditLogger history;
  found and fixed a real gap where delegation audit records never
  carried cost_usd despite DelegationRecord having it since Priority
  17.5); `ExecutiveDashboard` (executive_dashboard.py, Parts 23/27 --
  a thin real aggregator over every Foundation-tier component's own
  summary(), not a new cognitive layer -- ExecutiveRuntime already is
  that). Parts 24 (Multi-Agent Supervision) and 25 (Project Management)
  already satisfied by existing Orchestrator/DelegationEngine/Planner
  and ProjectStore -- not rebuilt, avoiding duplicated abstractions.

  Contract/integration-boundary only (Parts 6-8, 15-17, 21 -- Voice,
  Vision, OCR, Spatial Intelligence, Environmental Awareness, Browser/
  Computer Control, Application Control, Android/ADB, IoT, Sensors,
  Robotics, Home Assistant, MQTT): `PerceptionEngine` (perception.py --
  zero registered capture sources by default, observe() on an
  unconfigured source raises PerceptionSourceNotConfiguredError, the
  same ADAPTER READY pattern email_adapter.py established; never a
  background capture daemon) and `EmbodimentController`
  (embodiment.py -- request() computes risk via Layla's own real
  risk.classify_risk() and enforces ApprovalManager before any
  executor is looked up or called: structural, not name-matched,
  deliberately closing the exact bug class -- a tool-naming mismatch
  silently disabling a safety gate -- this mission's forensic audit
  found in the external codebase it studied; zero executors registered
  by default). Per the mission directive's own explicit fallback
  instruction for capabilities that cannot be safely fully implemented
  in this pass: neither module fabricates a working backend.

  82 new tests -- 299 total for Layla, up from 217, zero regressions
  at every commit. CONTRACT.md SS21-30, README.md, ROADMAP.md updated;
  ADR-0027 recorded in DECISIONS.md.

[Unreleased]: https://github.com/avishkar-labs/avishkar-os/compare/HEAD
