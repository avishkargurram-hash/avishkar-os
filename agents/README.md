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
`core/`, `router/` (model selection), optionally `mcp/`, `memory/`,
`knowledge/` depending on the agent's declared tools/context needs.

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

All documented to the 30-section template (STANDARDS.md §2.3 / ADR-0010).

## Limitations
4 of the 11 locked-roster agents (ADR-0007) exist as of Phase 13 (in
progress). The remaining 7 (Education & Knowledge, Research &
Intelligence, Finance & Economics, Government & Public Policy, Human
Development & Psychology, Creative & Media, Orchestrator) are built
one at a time — see ROADMAP.md.

## Future improvements
- An agent registry/index once there are enough agents that browsing
  directories stops being sufficient.
