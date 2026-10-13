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
The step engine (`WorkflowSpec`, `WorkflowEngine`, `Step`, and the
agent/knowledge/memory bridges) lives inside
[`factories/workflow-factory/python/avishkar_workflow/`](../factories/workflow-factory/python/avishkar_workflow/)
rather than duplicated here — the same precedent `memory/` and
`knowledge/` set. As of Phase 14, this shelf holds its first real,
product-facing workflow:
[`cross-domain-review/`](./cross-domain-review/README.md) — composes
any two real `ChiefDomainAgent`s (demonstrated with `legal-compliance`
+ `finance-economics`) into one synthesized, combined-perspective
summary.

## Limitations
One standalone workflow (`cross-domain-review/`) committed as of
Phase 14; sequential only (no fan-out), see that workflow's own
Limitations.

## Future improvements
- Additional named workflows as real cross-agent needs are identified
  — built when needed, not speculatively.
