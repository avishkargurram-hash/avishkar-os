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

[Unreleased]: https://github.com/avishkar-labs/avishkar-os/compare/HEAD
