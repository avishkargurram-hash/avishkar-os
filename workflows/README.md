# workflows/

## Purpose
The library of finished, reusable multi-step workflows — the output of
[`factories/workflow-factory`](../factories/workflow-factory/README.md),
composing agents, graphs, and automations into a repeatable process.

## Responsibilities
- One directory per workflow (`workflows/<name>/`), referencing the
  specific agents (`agents/`), graphs (`langgraph/`), and/or flows
  (`automation/`) it composes.
- Document the control flow (steps, branches, retry/error policy) so a
  product can adopt a workflow without reading its implementation.

## What does NOT belong here
- Orchestration engine logic itself — that's `langgraph/` (in-process
  agentic graphs) or `automation/` (n8n operational flows). A workflow
  here composes those; it doesn't reimplement them.
- Product-specific business processes — those live in the product repo,
  optionally built by composing workflows from here.

## Inputs
Output from `workflow-factory` only.

## Outputs
Reusable, composable workflows for any product.

## Dependencies
`agents/`, `langgraph/`, `automation/`, `mcp/`.

## Examples
_(none yet.)_

## Limitations
Empty as of the initial scaffold (2026-08-06).

## Future improvements
- None planned beyond what's tracked in `workflow-factory`'s README.
