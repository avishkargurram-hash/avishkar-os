# Evaluation Framework

## Vision
`agent-factory` (Phase 3) already gates a reasoning loop with
`QualityGate.check() -> bool`; `prompt-factory` (Phase 8, ADR-0014)
already scores rendered text against `EvalCase`s. Evaluation Framework
is the general-purpose suite runner and regression gate that sits on
top of — and reuses verbatim — that same scoring vocabulary, extended
to agents and workflows: one canonical way to ask "is this good enough
to ship," usable anywhere in the platform.

## Architecture
```
factories/evaluation-factory/python/avishkar_evaluation/
├── types.py            EvalSuite (+ EvalCase/EvalReport/RegressionResult/Scorer reused from avishkar_prompt)
├── runner.py             run_suite() / passes_threshold()
├── scorers.py              length_bounds_scorer / weighted_keyword_scorer
├── agent_bridge.py          make_quality_gate() -> avishkar_agent.QualityGate
└── workflow_bridge.py        evaluate_workflow_result()
```
See [CONTRACT.md](./CONTRACT.md) §0 for the full reuse story with
`prompt-factory` and `agent-factory`.

## Interfaces
`EvalSuite(name, cases)`. `run_suite(suite, subject_fn, scorer) ->
EvalReport`. `passes_threshold(report, threshold) -> bool`.
`make_quality_gate(name, suite, scorer, threshold) -> QualityGate`.
`evaluate_workflow_result(result, suite, scorer, output_key="output")
-> EvalReport`.

## Folder Structure / Naming Standards
See tree above; [STANDARDS.md](../../STANDARDS.md) §3.

## Extension Model
A new `Scorer` is a plain function, same shape `prompt-factory`
established. A new bridge (e.g. scoring a `knowledge-factory` search
result set) is a small module following `agent_bridge.py`/
`workflow_bridge.py`'s pattern: import the target framework's public
type, write one function, done.

## Examples
`python factories/evaluation-factory/examples/quickstart.py` — builds a
real `ChiefDomainAgent` whose `QualityGate` is produced by
`make_quality_gate()` (the agent's own reasoning loop is genuinely
gated by this framework, not a hand-written stand-in), evaluates a
`WorkflowResult`, and compares two reports via the reused
`compare_versions()`.

## Best Practices
- Reach for `run_suite()` directly for anything that isn't a prompt
  render or an agent/workflow result — it's the general form; the
  `agent_bridge`/`workflow_bridge` functions are convenience wrappers
  around it, not a different mechanism.
- Set `threshold` deliberately per use case: `1.0` for a hard
  correctness bar (e.g. `exact_match_scorer` on a deterministic
  template), lower for a soft quality signal (e.g.
  `keyword_presence_scorer` on open-ended generation).

## Anti-Patterns
- Defining a second `EvalCase`/`EvalReport`-shaped type instead of
  importing `avishkar_prompt`'s — the entire point of this framework is
  one scoring vocabulary shared across prompts, agents, and workflows;
  a parallel type would fragment that immediately.
- Using `make_quality_gate()`'s gate as the *only* check on an agent
  meant to run unattended in production — it gates one candidate output
  per iteration against a fixed suite; it isn't a substitute for human
  review of a genuinely high-stakes action (that's `ApprovalGate`,
  already in `agent-factory`).

## Testing Strategy
16 tests: `run_suite`/`passes_threshold` (averaging, empty-suite
error, threshold pass/fail), both new scorers (bounds, weighted
keywords including case-insensitivity and the zero-weights edge case),
`make_quality_gate` against real `AgentResult`s (pass, fail, name
propagation), and `evaluate_workflow_result` (default and custom
`output_key`).

## Limitations
- **No model-graded (LLM-as-judge) scorer yet** — every scorer here is
  rule-based (exact match, keyword presence/weighting, length bounds).
  A model-graded scorer needs a router call and its own cost/latency
  tradeoffs; real future work, not silently promised.
- **No persisted eval history** — `run_suite()` returns one `EvalReport`
  per call; tracking scores over time/versions is left to the caller
  (e.g. store reports via `memory-factory`) rather than built in here.

## Future Roadmap
- A model-graded `Scorer` once a dedicated grading-model convention
  exists in `router/`.
- Persisted eval history + a real regression-suite-as-CI-gate runner
  (fail a build if `passes_threshold()` regresses vs. the last run).
- A `knowledge_bridge` scoring retrieval quality (precision/recall over
  a `KnowledgeBase.search()` call), following the same pattern as
  `agent_bridge`/`workflow_bridge`.
