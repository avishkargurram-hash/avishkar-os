# Agent Factory

## Purpose
Generates new Chief Domain Agents: the blueprint schema, scaffolding CLI,
and validation that turns a domain spec into a production-ready agent
landing in [`agents/`](../../agents/README.md). This is the mold, not the
agents themselves — see [ARCHITECTURE.md](../../ARCHITECTURE.md) §2.

## Responsibilities
- Define the Chief Domain Agent blueprint schema (domain, supported expert
  roles, tools/MCP servers it may use, memory/knowledge dependencies,
  eval suite reference).
- Scaffold a new agent's directory structure and boilerplate from a
  blueprint.
- Validate a blueprint before scaffolding: reject specs that duplicate an
  existing Chief Agent's domain, or that define a role instead of a domain
  (per ARCHITECTURE.md §4 — roles are absorbed, not spun up as new agents).
- Wire a scaffolded agent to `router/` (model selection) and
  `evaluation-factory` (so it ships evaluable, not just runnable).

## Architecture
_(To be designed in Phase 1 — see [ROADMAP.md](../../ROADMAP.md).)_
Expected shape: `blueprint.schema.json` + a CLI (`avishkar agent new`) that
reads a blueprint, scaffolds into `agents/<domain>/`, and registers the new
agent with `core/`'s module loader.

## Inputs
A Chief Domain Agent blueprint (domain name, expert roles, tool/MCP
dependencies, target eval suite).

## Outputs
A scaffolded, documented agent package under `agents/<domain>/`, ready for
a human/agent engineer to implement and harden.

## Dependencies
`core/` (module lifecycle/loading), `router/` (model selection contract),
`evaluation-factory` (eval harness contract), optionally `mcp-factory`
output if the agent needs tools.

## Examples
_(none yet — first example lands with the Phase 1 agent-factory
implementation.)_

## Limitations
Not implemented yet. This README defines the contract the implementation
must satisfy.

## Future improvements
- Blueprint linting in CI so a bad spec fails before scaffolding.
- Auto-suggest an existing Chief Agent to absorb a role, given a proposed
  blueprint that looks like a role rather than a domain.
