# Security Factory

## Purpose
Produces security review tooling, threat-model templates, and guardrail
policies applied across the platform. Like `evaluation-factory`, this
factory has **no matching top-level library shelf** — its output is
consumed directly inside `core/`, `router/`, `mcp-factory`, `n8n-factory`,
and each product, not collected separately. See
[ARCHITECTURE.md](../../ARCHITECTURE.md) §2.

## Responsibilities
- Maintain the guardrail/threat-model checklist referenced from
  [STANDARDS.md](../../STANDARDS.md) §6, applied to every MCP server and
  agent tool that touches external systems before it's marked reusable.
- Provide reusable guardrail policies (input validation, output filtering,
  rate limiting, PII handling) that `mcp-factory` and `agent-factory`
  apply by default, not bolt on later.
- Own the secret-handling convention (`.env.template` pattern, what must
  never be committed — see `.gitignore` and STANDARDS.md §6).

## Architecture
_(To be designed in Phase 5 — see [ROADMAP.md](../../ROADMAP.md); note
Phase 5 also retroactively reviews everything built in earlier phases.)_
Expected shape: a checklist/lint tool runnable in CI against any
factory-generated MCP server or agent, plus a small library of guardrail
policy implementations other factories import.

## Inputs
A module/server/agent to review, or a guardrail policy spec.

## Outputs
A pass/fail security review result, or a reusable guardrail policy
implementation imported by `mcp-factory`/`agent-factory` output.

## Dependencies
`core/` only.

## Examples
_(none yet.)_

## Limitations
Not implemented yet. Every factory currently references this checklist
aspirationally — it must exist before any factory output is genuinely
considered "reusable" and safe, per STANDARDS.md §6.

## Future improvements
- Automated CI gate blocking merge of any new MCP server/agent tool that
  hasn't passed the checklist.
