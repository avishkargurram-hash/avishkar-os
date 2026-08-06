# router/ — AI Router

## Purpose
The single place in the platform that decides "which model/provider
handles this request." Unlike the other library shelves, the Router isn't
produced by a factory — it's a standalone core capability of Avishkar OS,
listed as its own top-level item in the platform's capability list.

## Responsibilities
- Model/provider selection per request (cost, latency, capability,
  availability constraints).
- Fallback chains when a preferred model/provider fails or is
  rate-limited.
- Usage/cost tracking hooks so every product's model spend is visible
  centrally, not siloed per product.
- A stable interface every agent, workflow, and factory-generated module
  calls through — no module should call a model provider's SDK directly.

## What does NOT belong here
- Provider-specific business logic beyond routing (e.g. a product's
  prompt content) — that's the calling agent's/product's concern.

## Architecture
_(To be designed in Phase 2 — see [ROADMAP.md](../ROADMAP.md).)_ Expected
shape: a routing policy config (rules/weights per model/provider) plus a
thin client interface (`route(request) -> response`) that `agents/`,
`langgraph/`, `knowledge-factory`, and `prompt-factory` all depend on.

## Inputs
A model-capability request (task type, constraints, calling module
identity for cost attribution).

## Outputs
A response from the selected model/provider, plus routing/cost metadata.

## Dependencies
`core/` only.

## Examples
_(none yet.)_

## Limitations
Not implemented yet. As of the initial scaffold, no module in this repo
has a routing layer to depend on — this is a Phase 2 priority precisely
because so much else depends on it.

## Future improvements
- Per-product cost budgets and alerting once multiple products are live.
