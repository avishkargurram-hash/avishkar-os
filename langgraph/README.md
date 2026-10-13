# langgraph/

## Purpose
The library of reusable LangGraph graphs for stateful, multi-step agentic
patterns — the output of
[`factories/langgraph-factory`](../factories/langgraph-factory/README.md).

## Responsibilities
- One directory per graph (`langgraph/<name>/`), documenting its nodes,
  transitions, and state schema.
- Provide proven, reusable patterns (plan-execute, reflect-and-retry,
  multi-agent handoff) that `workflow-factory` and agents can compose
  rather than reimplementing graph logic ad hoc.

## What does NOT belong here
- Graph-generation logic — that's `langgraph-factory`.
- A one-off graph specific to a single product's process — belongs in
  that product's repo unless it proves reusable, at which point it's
  promoted here deliberately.

## Inputs
Output from `langgraph-factory` only.

## Outputs
Importable, reusable graphs for agents and workflows.

## Dependencies
`router/`, `memory/`, `core/`.

## Examples
_(none yet.)_

## Limitations
Empty as of the initial scaffold (2026-08-06).

## Future improvements
- None planned beyond what's tracked in `langgraph-factory`'s README.
