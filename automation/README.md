# automation/

## Purpose
The library of reusable n8n automation flows for operational work
(integrations, scheduled jobs, notification pipelines) — the output of
[`factories/n8n-factory`](../factories/n8n-factory/README.md).

## Responsibilities
- One directory per flow (`automation/<name>/`), holding the exported flow
  definition with parameterized (never embedded) credentials.
- Cover operational/integration automation — not in-process agent
  reasoning, which belongs in `langgraph/`.

## What does NOT belong here
- Flow-generation logic — that's `n8n-factory`.
- Embedded credentials of any kind — see `.gitignore` and
  [STANDARDS.md](../STANDARDS.md) §6.
- Agentic multi-step reasoning workflows — those are `langgraph/` graphs
  or `workflows/` compositions, not n8n flows.

## Inputs
Output from `n8n-factory` only.

## Outputs
Importable n8n flows for operational use across products.

## Dependencies
`security-factory` (credential-handling review), `core/`.

## Examples
_(none yet.)_

## Limitations
Empty as of the initial scaffold (2026-08-06).

## Future improvements
- None planned beyond what's tracked in `n8n-factory`'s README.
