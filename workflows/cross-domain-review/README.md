# cross-domain-review

## Purpose
A real, reusable two-agent review workflow — the first concrete shelf
artifact under `workflows/` (Phase 14), rather than only an example
living inside `factories/workflow-factory`. Gets one agent's
perspective, then a second's, then synthesizes both into one combined
summary — the pattern behind "get a legal and a financial read on
this" and similar cross-domain review needs.

## Responsibilities
- Compose any two real `ChiefDomainAgent` instances (not a fixed pair
  — the built-in example pairs `legal-compliance` with
  `finance-economics`, but `build_cross_domain_review_workflow` takes
  any two agents).
- Run both agents and combine their outputs into one labeled summary.

## Architecture
`build_cross_domain_review_workflow(first_agent, second_agent) ->
WorkflowSpec` — three `workflow-factory` `Step`s: `first_review` and
`second_review` (each `make_agent_step`, Phase 7's bridge into
`agent-factory`), then `synthesize` (a plain function combining both
results). `run_cross_domain_review(first_agent, second_agent,
input_text) -> WorkflowResult` builds the spec and runs it in one
call. No new architecture — pure composition of Phase 7's
`WorkflowEngine` over Phase 3's `ChiefDomainAgent`.

## Interfaces
`build_cross_domain_review_workflow(first_agent, second_agent) ->
WorkflowSpec`. `run_cross_domain_review(first_agent, second_agent,
input_text) -> WorkflowResult` — `result.state["summary"]` holds the
combined text; `result.history` is `("first_review", "second_review",
"synthesize")` on success.

## Dependencies
`core/`, `factories/agent-factory` (for `ChiefDomainAgent`),
`factories/workflow-factory` (for `Step`/`WorkflowSpec`/
`WorkflowEngine`/`make_agent_step`).

## Inputs
Two real `ChiefDomainAgent` instances and one input string.

## Outputs
A `WorkflowResult` whose `state["summary"]` is both agents' outputs,
labeled by agent name.

## Examples
`python workflows/cross-domain-review/examples/quickstart.py` — runs
the real `legal-compliance` and `finance-economics` agents (Phase 13)
through this workflow on a sample vendor-contract question.

## Limitations
Sequential, not parallel — `second_review` only starts after
`first_review` completes (`WorkflowEngine`'s own current limitation,
`workflow-factory/README.md` Limitations). Exactly two agents; a
three-or-more-agent version would need a different `synthesize` step,
not built speculatively here.

## Future Roadmap
- A parallel variant once `WorkflowEngine` supports fan-out/fan-in
  (tracked in `workflow-factory`'s own Future Roadmap).
- An N-agent variant (`Orchestrator.broadcast()` + a synthesis step)
  once a real need for more than two perspectives appears.
