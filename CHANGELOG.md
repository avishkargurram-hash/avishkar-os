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

[Unreleased]: https://github.com/avishkar-labs/avishkar-os/compare/HEAD
