# mcp/

## Purpose
The library of reusable MCP (Model Context Protocol) servers — the output
of [`factories/mcp-factory`](../factories/mcp-factory/README.md) — that
agents and products can mount to gain tool/resource access.

## Responsibilities
- One directory per MCP server (`mcp/<name>/`), documenting exposed tools,
  resources, and auth requirements.
- Every server here has passed `security-factory`'s guardrail checklist
  (see [STANDARDS.md](../STANDARDS.md) §6) before being marked reusable.

## What does NOT belong here
- Server-generation logic — that's `mcp-factory`.
- A product-specific integration only that product needs — lives in the
  product's repo, optionally built with `mcp-factory` tooling but not
  committed here.

## Inputs
Output from `mcp-factory` only, security-reviewed.

## Outputs
Mountable MCP servers for agents to declare as tool dependencies.

## Dependencies
`core/`, `security-factory` (review gate).

## Examples
_(none yet.)_

## Limitations
Empty as of the initial scaffold (2026-08-06).

## Future improvements
- None planned beyond what's tracked in `mcp-factory`'s README.
