# agents/

## Purpose
The library of production, reusable **Chief Domain Agents** — the finished
output of [`factories/agent-factory`](../factories/agent-factory/README.md).
Any product can import an agent from here directly; nothing here is
generator code.

## Responsibilities
- Hold one directory per Chief Domain Agent (`agents/<domain>/`), each
  supporting multiple expert roles internally (see
  [ARCHITECTURE.md](../ARCHITECTURE.md) §4) rather than one directory per
  narrow task.
- Each agent package owns its blueprint, implementation, and its eval
  suite reference (via `evaluation-factory`).

## What does NOT belong here
- Generator/scaffolding logic — that's `factories/agent-factory`.
- Product-specific agent configuration or fine-tuning for one app — that
  lives in the product's own repo, configuring an agent from here, not
  forking it.

## Inputs
New agents arrive here only as `agent-factory` output, hardened and
reviewed — not hand-added ad hoc.

## Outputs
Importable Chief Domain Agents for any product built on Avishkar OS.

## Dependencies
`core/`, `router/` (model selection). As of Phase 13, every agent but
`software-ai-engineering` also depends on `memory-factory`,
`knowledge-factory`, `evaluation-factory`, and `security-factory` for
real (not just declared) integration; `mcp/` remains a declared-only
seam until a real MCP server exists (Phase 4's `mcp-factory` is built,
but no server-side implementation for any of these agents' declared
tools is).

## Examples
- [`software-ai-engineering/`](./software-ai-engineering/README.md) — the
  first Chief Domain Agent, built on `agent-factory` (ROADMAP.md Phase 3).
- [`medical-healthcare/`](./medical-healthcare/README.md) — Phase 13;
  `SQLiteMemoryPolicy`, a real `KnowledgeBase`, `evaluation-factory`/
  `security-factory` integration.
- [`legal-compliance/`](./legal-compliance/README.md) — Phase 13;
  `FileMemoryPolicy` (proving cross-instance persistence with a
  different backend than medical-healthcare's), a real `KnowledgeBase`.
- [`startup-business-product/`](./startup-business-product/README.md) —
  Phase 13; `SQLiteMemoryPolicy`, a real `KnowledgeBase`.
- [`education-knowledge/`](./education-knowledge/README.md) — Phase 13;
  `FileMemoryPolicy`, a real `KnowledgeBase`.
- [`research-intelligence/`](./research-intelligence/README.md) —
  Phase 13; `SQLiteMemoryPolicy`, a real `KnowledgeBase`.
- [`finance-economics/`](./finance-economics/README.md) — Phase 13;
  `FileMemoryPolicy`, a real `KnowledgeBase`, plus
  `make_rate_limit_guardrail()` (a different `security-factory`
  bridge than the other agents use).
- [`government-public-policy/`](./government-public-policy/README.md) —
  Phase 13; `SQLiteMemoryPolicy`, a real `KnowledgeBase`.
- [`human-development-psychology/`](./human-development-psychology/README.md) —
  Phase 13; `FileMemoryPolicy`, a real `KnowledgeBase`, and this
  repository's most safety-critical guardrail (`crisis-escalation`,
  whose block reason carries real crisis-resource contact information).
- [`creative-media/`](./creative-media/README.md) — Phase 13;
  `SQLiteMemoryPolicy`, a real `KnowledgeBase`.
- [`orchestrator/`](./orchestrator/README.md) — Phase 13; the
  coordination seat, no `blueprint.json` by design (§1 of its README)
  — composes `avishkar_agent.Orchestrator` over real instances of all
  10 domain agents above.

All documented to the 30-section template (STANDARDS.md §2.3 / ADR-0010).

## Limitations
All 11 locked-roster agents (ADR-0007) exist as of Phase 13 — the
roster is complete. Future improvements (real `prompt-factory`/
`template-factory` migration, richer MCP resolution once real servers
exist) are tracked in each agent's own README §30, not here.

## Future improvements
- An agent registry/index once there are enough agents that browsing
  directories stops being sufficient.
