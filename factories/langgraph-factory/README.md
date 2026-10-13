# LangGraph Factory

## Purpose
Generates reusable [LangGraph](https://langchain-ai.github.io/langgraph/)
graph scaffolds for stateful, multi-step agentic patterns — the tooling
behind reusable graphs landing in [`langgraph/`](../../langgraph/README.md).

## Responsibilities
- Provide graph scaffolds for common agentic patterns (e.g. plan-execute,
  reflect-and-retry, multi-agent handoff) so a new graph starts from a
  proven shape, not a blank canvas.
- Wire generated graphs to `router/` for model selection per node and to
  `memory/` for state persistence, rather than each graph inventing its
  own.
- Validate a new graph spec against existing graphs to avoid near-duplicate
  patterns.

## Architecture
_(To be designed in Phase 3.)_ Expected shape: parameterized graph
templates (Python) with node/edge definitions kept declarative where
possible, so `workflow-factory` can compose them without reading
implementation details.

## Inputs
A graph spec: nodes, transitions, state schema, which pattern template to
start from.

## Outputs
A scaffolded graph package in `langgraph/<name>/`.

## Dependencies
`router/`, `memory-factory` output (`memory/`), `core/`.

## Examples
_(none yet.)_

## Limitations
Not implemented yet.

## Future improvements
- Visual graph preview generation for docs/onboarding.
