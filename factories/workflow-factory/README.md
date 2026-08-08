# Workflow Framework

## Vision
Agents (Phase 3), memory (Phase 5), and knowledge (Phase 6) are each
real and composable on their own — but a product needs to *sequence*
them: search knowledge, ask an agent, remember the answer, branch on
the result. Workflow Framework is that step engine: an in-process,
stdlib-only runtime whose steps are plain LangGraph-shaped functions
(`Callable[[State], PartialState]`), with real bridges into the three
frameworks it composes.

## Architecture
```
factories/workflow-factory/python/avishkar_workflow/
├── types.py      State/PartialState/NodeFn/Step/WorkflowResult (+ reused RetryPolicy)
├── workflow.py    WorkflowSpec (validated graph) + WorkflowEngine (runner)
├── bridges.py      make_agent_step / make_knowledge_search_step / make_memory_*_step
└── errors.py       WorkflowFrameworkError and subclasses
```
See [CONTRACT.md](./CONTRACT.md) for the full contract, including why
`langgraph-factory`/`n8n-factory` stay deferred (§0).

## Interfaces
`WorkflowSpec(id, steps, start)` validates structure eagerly.
`WorkflowEngine().run(spec, initial_state, max_steps=1000) ->
WorkflowResult`. `Step(id, handler, next=, branch=, retry_policy=)`.
Bridges: `make_agent_step(agent)`, `make_knowledge_search_step(kb)`,
`make_memory_read_step(memory, kind, ...)`,
`make_memory_write_step(memory, kind, ...)`.

## Folder Structure / Naming Standards
See tree above; [STANDARDS.md](../../STANDARDS.md) §3.

## Extension Model
Any callable matching `Callable[[State], PartialState]` is a valid
step — no base class to subclass, no registration required. New
bridges (e.g. a future `make_mcp_call_step` wrapping
`avishkar_integration.ToolRuntime` directly) are added the same way
the three shipped ones were: a small function in `bridges.py`.

## Examples
`python factories/workflow-factory/examples/quickstart.py` — a real
5-step workflow: search a `KnowledgeBase`, build a question from the
result, ask a `ChiefDomainAgent`, extract its answer, and write it to
an `InMemoryMemoryPolicy` — then reads it back to prove the round trip.

## Best Practices
- Keep step handlers small and single-purpose; use `branch` for
  control flow rather than smuggling `if`/`else` into a handler that
  also does work — it keeps the workflow's shape legible from the
  `WorkflowSpec` alone.
- Set `retry_policy` on steps that call something that can transiently
  fail (a tool call, a model request); leave the default
  (`max_attempts=1`) on pure in-memory transforms.

## Anti-Patterns
- Mutating the incoming `state` mapping inside a handler instead of
  returning a partial update — breaks the "pure function" contract
  that makes steps trivially testable and reusable as LangGraph nodes.
- Building a bespoke retry loop inside a handler instead of using
  `Step.retry_policy` — duplicates what the engine already does and
  won't show up in `WorkflowResult`'s failure semantics consistently.

## Testing Strategy
17 tests: `WorkflowSpec` construction validation (duplicate ids,
unknown start/next), linear execution and state merging, branching
(including branch-to-unknown-step and branch-returning-None), retry
(success-after-flakiness and exhaustion, both via an injectable
`sleep_fn` so tests run in milliseconds, not real backoff time), the
cycle guard, and all three integration bridges against real
`ChiefDomainAgent`/`KnowledgeBase`/`InMemoryMemoryPolicy` instances.

## Limitations
- **No persistence** — a `WorkflowResult`/in-flight run isn't
  serializable or resumable today; a crash mid-run loses progress.
  Pairing with `memory-factory`'s persistent backends for checkpointing
  is a real option a caller can build today (write state to memory
  after each step); the engine doing it automatically is Future
  Roadmap.
- **No parallel steps** — the engine is strictly single-threaded,
  one step at a time. Fan-out/fan-in is a real gap, not hidden.
- **`schemas/workflow-spec.schema.json` is structural, not
  executable** — see CONTRACT.md §8 for why handler/branch resolution
  from a serialized spec is deliberately not attempted yet.

## Future Roadmap
- Checkpointed/resumable runs (persist `WorkflowResult` after each
  step via a `memory-factory` backend).
- Parallel step execution (fan-out to N steps, fan-in on completion).
- A `make_tool_call_step` bridge directly wrapping
  `avishkar_integration.ToolRuntime` for MCP/REST tool calls inside a
  workflow, not just inside an agent.
- Once `langgraph-factory` is un-deferred (a future ADR, per ADR-0009),
  a documented adapter from `WorkflowSpec` to a real `StateGraph`.
