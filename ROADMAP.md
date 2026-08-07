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

## Phase 1 — Core Engine Framework (`core/`)

Goal: build the one framework everything else depends on, completely,
before anything else starts — nothing after this phase can be genuinely
"done" without it, since every other framework's README declares a
dependency on it.

- 💤 `core/`: config, logging, event bus, module lifecycle/registry
- 💤 `core/` documented to the Framework template (STANDARDS.md §2.2) with
  real Interfaces and a runnable Example
- 💤 Locked (✅) before Phase 1.5 starts

## Phase 1.5 — Agent Framework + first Chief Domain Agent (`agent-factory`)

Goal: prove the Factory → Library pattern (ADR-0002) end-to-end with one
real Chief Domain Agent before replicating it 10 more times.

- 💤 `agent-factory`: blueprint schema, CLI scaffold
- 💤 First Chief Domain Agent built completely to the §2.3 template
  (candidate: Software & AI Engineering — nearest to this platform's own
  needs) landing in `agents/`
- 💤 `evaluation-factory`: minimal harness to eval that first agent
- 💤 First ADR-validated example of a product consuming `agents/` output

## Phase 2 — Routing & Memory (`router/`, `memory-factory`, `knowledge-factory`)

- 💤 AI Router: provider/model selection, fallback chains, cost tracking
- 💤 `memory-factory` + first shared memory backend in `memory/`
- 💤 `knowledge-factory` + first shared knowledge base in `knowledge/`

## Phase 3 — Orchestration & Automation (`langgraph-factory`, `n8n-factory`, `workflow-factory`, `mcp-factory`)

- 💤 First reusable LangGraph graph in `langgraph/`
- 💤 First reusable MCP server in `mcp/`
- 💤 First reusable n8n flow in `automation/`
- 💤 `workflow-factory` composing the above into a multi-step workflow

## Phase 4 — Product enablement (`project-factory`, `starter-kit-factory`, `prompt-factory`, `template-factory`)

- 💤 `project-factory` can scaffold a new product repo pre-wired to
  Avishkar OS
- 💤 First starter kit in `starters/`
- 💤 `prompt-factory` + `template-factory` producing versioned, evaluable
  assets
- 💤 First real product (candidate: whichever of Tryvanta / Humanify OS /
  GENESIS / Muziclly / AI Atlas / Coupler is nearest to build) scaffolded
  from a starter kit and running on Avishkar OS
- 💤 Remaining 9 Chief Domain Agents + Orchestrator built out, one at a
  time, per the locked roster (ARCHITECTURE.md §4 / ADR-0007) — order
  driven by which product needs which domain first, not alphabetically

## Phase 5 — Security & Documentation hardening (`security-factory`, `documentation-factory`)

- 💤 Guardrail policy templates and threat-model checklist
- 💤 Every existing factory's output reviewed against the security
  checklist retroactively
- 💤 `documentation-factory`: doc-coverage lint (every folder has a README
  matching its correct template tier), ADR tooling
- 💤 Every existing framework/module's README checked against the correct
  STANDARDS.md §2 template tier retroactively

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
