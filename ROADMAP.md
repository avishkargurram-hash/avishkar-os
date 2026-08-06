# Roadmap

Status legend: ✅ Built · 🚧 In progress · 📋 Planned · 💤 Not started

This roadmap tracks the platform itself, not any single product built on
top of it. Update it when a phase's status actually changes — not on a
schedule.

## Phase 0 — Foundation (current)

Goal: a repository that can't be built on top of by mistake, because its
contracts are written down before its code is.

- ✅ Repository structure, standards, architecture, decision log
- ✅ `CLAUDE.md` master constitution
- ✅ Per-module README contracts (purpose stated, implementation pending)
- 💤 CI scaffold (lint, type-check, test, doc-coverage gate)
- 💤 `CONTRIBUTING.md` workflow validated with a real first PR

## Phase 1 — Core Engine + first factory (`core/`, `agent-factory`)

Goal: prove the Factories vs. Library architecture (ADR-0002) end-to-end
with one real vertical slice before replicating the pattern twelve more
times.

- 💤 `core/`: config, logging, event bus, module lifecycle
- 💤 `agent-factory`: blueprint schema, CLI scaffold, one generated
  Chief Domain Agent landing in `agents/`
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

## Phase 5 — Security & hardening (`security-factory`)

- 💤 Guardrail policy templates and threat-model checklist
- 💤 Every existing factory's output reviewed against the security
  checklist retroactively

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
