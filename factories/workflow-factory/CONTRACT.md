# Workflow Framework — Contract

Language-agnostic contract for the Workflow Framework. The Python
reference implementation is `avishkar_workflow`
(`factories/workflow-factory/python/`); any other language implementing
this contract must satisfy the same shapes.

## §0. Relationship to `langgraph-factory` and `n8n-factory`

Per ADR-0009, `langgraph-factory` (LangGraph-native orchestration as a
first-class execution engine) and `n8n-factory` (operational automation
flows) remain deferred — this framework does not un-defer either. What
it ships instead, per the same "shape without the dependency" playbook
ADR-0011 used for `mcp-factory`'s `langgraph_nodes` module: a real,
runnable, in-process **step engine** whose steps are plain
`Callable[[State], PartialState]` — the exact shape a LangGraph node
already has — with zero import of the `langgraph` or `n8n` packages.
A caller who has `langgraph` installed can wire a `WorkflowSpec`'s steps
directly into their own `StateGraph` as nodes; a caller who wants n8n
gets there by exporting the spec, not by this framework depending on
either.

## §1. State

`State = Mapping[str, Any]`. A step receives the accumulated state and
returns a **partial** update (`Mapping[str, Any]`) that is shallow-
merged into it — identical semantics to a LangGraph node, deliberately.

## §2. Step

A `Step` is:
- `id: str` — unique within a `WorkflowSpec`.
- `handler: Callable[[State], Mapping[str, Any]]` — does the work.
- `next: Optional[str]` — the step id to run next; `None` ends the
  workflow. Statically validated against the spec's step ids at
  `WorkflowSpec` construction time.
- `branch: Optional[Callable[[State], Optional[str]]]` — if present,
  called **instead of** `next` after `handler` runs, with the
  post-merge state; its return value (a step id, or `None` to end) is
  not statically validatable since it's data-dependent, and is checked
  at run time (`UnknownStepError` if it names a step that doesn't
  exist).
- `retry_policy: RetryPolicy` — reused verbatim from
  `avishkar_integration.RetryPolicy` (Phase 4), not redefined. A step
  whose `handler` raises is retried up to `max_attempts` times with
  `backoff_seconds` between attempts before the workflow fails.

## §3. WorkflowSpec

`WorkflowSpec(id, steps, start)` — `steps` is a collection of `Step`;
`start` names the first step. Construction validates: step ids are
unique (`DuplicateStepError`), `start` and every static `next` target
exist among the step ids (`UnknownStepError`).

## §4. WorkflowEngine

`WorkflowEngine().run(spec, initial_state, *, max_steps=1000) ->
WorkflowResult`. Executes steps starting at `spec.start`, following
`branch` (if set) or else `next`, merging each step's partial update
into cumulative state, and recording an ordered `history` of step ids
executed. Raises `MaxStepsExceededError` if `max_steps` is exceeded — a
cycle guard, since `branch` can create dynamic cycles a static check
can't catch. Never silently swallows a step's exception: after retries
are exhausted, the engine raises `StepExecutionError` (chaining the
original exception) rather than returning a partial, silently-wrong
result — `WorkflowResult.status` only ever reports `"completed"` for a
run that actually reached a step with no next step.

## §5. WorkflowResult

`WorkflowResult(state, history, status)` — `status` is `"completed"`.
(A failed run raises rather than returning a `"failed"` result — see
§4 — so `status` is currently always `"completed"` on successful
return; the field is kept on the type for forward compatibility with a
future non-raising `run_safe()` variant, not because it varies today.)

## §6. Integration bridges (`avishkar_workflow.bridges`)

Closes the "compose agents, memory, and knowledge into a workflow"
requirement as a **consumer** of each earlier framework's already-public
types — no changes to `agent-factory`, `memory-factory`, or
`knowledge-factory` source (the same dependency-direction discipline as
ADR-0011 §3):

- `make_agent_step(agent, *, input_key="input", output_key="output")` —
  runs `agent.handle(Task(input=state[input_key]))` (`agent-factory`,
  Phase 3) and returns `{output_key: AgentResult}`.
- `make_knowledge_search_step(kb, *, query_key="query",
  results_key="knowledge_results", top_k=5)` — runs `kb.search(...)`
  (`knowledge-factory`, Phase 6).
- `make_memory_read_step(memory, kind, *, key_from_state,
  output_key)` / `make_memory_write_step(memory, kind, *,
  key_from_state, value_from_state)` — read/write through a
  `MemoryPolicy` (`memory-factory`/`agent-factory`, Phase 5).

## §7. Errors

`WorkflowFrameworkError` (base), `DuplicateStepError`,
`UnknownStepError`, `StepExecutionError`, `MaxStepsExceededError`.

## §8. Declarative spec (interop only)

[`schemas/workflow-spec.schema.json`](./schemas/workflow-spec.schema.json)
describes the **structural** shape of a workflow (step ids, `next`,
whether a step branches, retry policy) for cross-language documentation
and tooling. It intentionally does not attempt to serialize `handler`/
`branch` — those are language-native callables; a JSON-only "handler
reference" would either be a string naming a registry key (an extra
indirection layer no current caller needs) or an executable-code blob
(a real security liability this platform's security-first principle
rules out). Building that resolution layer is tracked as Future
Roadmap, not pretended to exist today.
