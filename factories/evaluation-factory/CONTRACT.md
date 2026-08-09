# Evaluation Framework — Contract

Language-agnostic contract for the Evaluation Framework. The Python
reference implementation is `avishkar_evaluation`
(`factories/evaluation-factory/python/`).

## §0. Relationship to `agent-factory`'s `QualityGate` and `prompt-factory`'s scoring seam

`agent-factory` (Phase 3) already ships a minimal, real self-evaluation
mechanism: `QualityGate.check(AgentResult) -> bool`, driving the
reasoning loop's iterate-until-passing behavior. `prompt-factory`
(Phase 8, ADR-0014) already ships a real scoring seam:
`EvalCase`/`EvalReport`/`RegressionResult`/`Scorer` plus two working
scorers. Per ADR-0014, this framework was always meant to **extend**
that seam, not replace it: `avishkar_evaluation` imports and re-exports
`EvalCase`/`EvalReport`/`RegressionResult`/`Scorer` from
`avishkar_prompt` verbatim (one canonical definition, used everywhere:
prompts, agents, workflows), and adds:
1. A general-purpose suite runner usable against *any* subject (a
   prompt render, an agent's output, a workflow's final state) — not
   just `PromptRegistry.render()`.
2. Two more real scorers (`length_bounds_scorer`,
   `weighted_keyword_scorer`).
3. A bridge that turns an `EvalSuite` into a real
   `avishkar_agent.QualityGate` — closing the loop so this framework's
   suites can gate a Chief Domain Agent's own reasoning loop, not just
   report a score after the fact.
4. A bridge that scores a `avishkar_workflow.WorkflowResult`.

## §1. EvalSuite

`EvalSuite(name, cases)` — a named, reusable collection of
`avishkar_prompt.EvalCase`s. Deliberately thin: an `EvalCase` already
has everything a case needs (`inputs`, `expected`); a suite just names
a set of them for reuse across runs.

## §2. Running a suite

`run_suite(suite, subject_fn, scorer) -> EvalReport` — for each `case`
in `suite.cases`, computes `actual = subject_fn(case)` then
`scorer(actual, case)`, and returns the averaged `EvalReport` (same
type `prompt-factory`'s `evaluate_version` returns — this is its
generalization: `evaluate_version` is equivalent to `run_suite` with
`subject_fn = lambda case: registry.render(name, case.inputs,
version=version)`). `EmptyCaseSetError` if `suite.cases` is empty —
an eval suite with no cases can't produce a meaningful score, and
silently returning `0.0` would look like a real failing score rather
than a configuration mistake.

`passes_threshold(report, threshold) -> bool` — `report.average >=
threshold`. The regression-gate primitive: `compare_versions` (reused
from `prompt-factory`) answers "did it get better?"; this answers "is
it good enough to ship?" — both are real, distinct questions a CI gate
needs.

## §3. Additional scorers

`length_bounds_scorer(min_length, max_length) -> Scorer` — `1.0` if
rendered text length is within `[min_length, max_length]`, else `0.0`.
`weighted_keyword_scorer(weights: Mapping[str, float]) -> Scorer` — sum
of weights for keywords present (case-insensitive) in the rendered
text, normalized by the sum of all weights; generalizes
`prompt-factory`'s unweighted `keyword_presence_scorer` for cases where
some required terms matter more than others.

## §4. Agent Framework bridge (`avishkar_evaluation.agent_bridge`)

`make_quality_gate(name, suite, scorer, threshold) ->
avishkar_agent.QualityGate` — the returned gate's `check(candidate)`
runs `run_suite(suite, lambda case: candidate.output, scorer)` and
returns `passes_threshold(report, threshold)`. A pure consumer of
`agent-factory`'s already-public `QualityGate` type — no changes to
`agent-factory`'s locked source, the same dependency-direction
discipline every later framework in this platform has followed since
`mcp-factory` (ADR-0011).

## §5. Workflow Framework bridge (`avishkar_evaluation.workflow_bridge`)

`evaluate_workflow_result(result, suite, scorer, *, output_key="output")
-> EvalReport` — scores `str(result.state[output_key])` against every
case in `suite` the same way `run_suite` does. A pure consumer of
`avishkar_workflow`'s already-public `WorkflowResult` type.

## §6. Errors

`EvaluationFrameworkError` (base), `EmptyCaseSetError`.
