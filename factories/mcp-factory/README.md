# MCP Factory

## Purpose
Generates MCP (Model Context Protocol) servers that expose tools and
resources to agents — the tooling behind reusable servers landing in
[`mcp/`](../../mcp/README.md).

## Responsibilities
- Define the MCP server spec: tools exposed, resources, auth requirements,
  which agents/products may mount it.
- Scaffold a new MCP server package with the security checklist from
  `security-factory` applied by default (auth, input validation, rate
  limiting stubs) — not bolted on later.
- Validate that a proposed server doesn't duplicate tools an existing
  server already exposes.

## Architecture
_(To be designed in Phase 3.)_ Expected shape: a server template per
supported language/runtime, with a manifest describing exposed
tools/resources that `agent-factory`-generated agents can declare a
dependency on.

## Inputs
An MCP server spec: name, tools/resources to expose, external systems it
touches, auth model.

## Outputs
A scaffolded MCP server package in `mcp/<name>/`.

## Dependencies
`security-factory` (guardrail/threat-model checklist — mandatory before a
server is marked reusable, per STANDARDS.md §6), `core/`.

## Examples
_(none yet.)_

## Limitations
Not implemented yet.

## Future improvements
- Auto-generated MCP tool documentation from the manifest, surfaced to
  `agent-factory` so agents can discover available tools.
