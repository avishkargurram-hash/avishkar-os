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
_(none yet — the first agent lands in Phase 1, see
[ROADMAP.md](../ROADMAP.md).)_

## Limitations
Empty as of the initial scaffold (2026-08-06). No Chief Domain Agent
exists yet because `agent-factory` doesn't exist yet.

## Future improvements
- An agent registry/index once there are enough agents that browsing
  directories stops being sufficient.
