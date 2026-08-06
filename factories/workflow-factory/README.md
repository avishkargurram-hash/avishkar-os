# Workflow Factory

## Purpose
Generates multi-step orchestrated workflows that compose agents, tools,
and MCP servers into a repeatable process — the tooling behind reusable
workflows landing in [`workflows/`](../../workflows/README.md).

## Responsibilities
- Define the workflow spec schema: ordered/branching steps, which agent or
  tool handles each step, error/retry policy, human-in-the-loop points.
- Scaffold a new workflow from a spec, wiring it to the agents
  (`agents/`), graphs (`langgraph/`), and automations (`automation/`) it
  composes.
- Validate that a workflow doesn't reimplement orchestration logic that
  `langgraph-factory` or `n8n-factory` already provides — a workflow
  composes existing primitives, it doesn't reinvent an execution engine.

## Architecture
_(To be designed in Phase 3.)_ Expected shape: a workflow spec (YAML/JSON)
compiled to either a LangGraph graph (for in-process agentic workflows) or
an n8n flow (for operational automation), depending on the workflow's
nature — this factory decides which backend fits, not the caller.

## Inputs
A workflow spec: steps, participants (agents/tools), control flow, backend
preference if any.

## Outputs
A workflow package in `workflows/<name>/`, plus the compiled
LangGraph graph or n8n flow it produced (also registered under
`langgraph/` or `automation/` respectively).

## Dependencies
`agent-factory` output (`agents/`), `langgraph-factory`, `n8n-factory`,
`mcp-factory` output (`mcp/`).

## Examples
_(none yet.)_

## Limitations
Not implemented yet.

## Future improvements
- Visual workflow diagram generation from the spec (for docs and
  onboarding).
