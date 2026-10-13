# n8n Factory

## Purpose
Generates reusable [n8n](https://n8n.io/) automation flows for operational
work (integrations, scheduled jobs, notification pipelines) — the tooling
behind reusable flows landing in [`automation/`](../../automation/README.md).

## Responsibilities
- Provide flow scaffolds for common operational patterns (webhook →
  process → notify; scheduled sync; approval pipeline).
- Keep n8n credentials/config as references, never embedded — flows
  exported from this factory must be safe to commit (see
  STANDARDS.md §6).
- Distinguish operational automation (belongs here) from in-process
  agentic orchestration (belongs in `langgraph-factory` /
  `workflow-factory`) — if a flow is really "agent reasoning through
  steps," it's in the wrong factory.

## Architecture
_(To be designed in Phase 3.)_ Expected shape: exported n8n flow JSON
templates with parameterized credentials, plus a thin import/export CLI.

## Inputs
A flow spec or an existing n8n flow to import and generalize.

## Outputs
A reusable flow package in `automation/<name>/`.

## Dependencies
`security-factory` (credential handling review), `core/`.

## Examples
_(none yet.)_

## Limitations
Not implemented yet.

## Future improvements
- CI check that no exported flow JSON contains embedded credentials.
