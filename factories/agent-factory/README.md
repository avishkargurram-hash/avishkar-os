# Agent Framework

## Vision
Every Chief Domain Agent in Avishkar OS must be a complete software
system — an inspectable reasoning loop with real memory, tools,
guardrails, and quality gates — never a system prompt wearing a job
title. Agent Framework is the runtime that makes that possible: it owns
the *mechanics* of agency (plan → act → reflect, sub-agent routing,
multi-agent coordination, human approval, quality gating) so a domain
module only has to supply *domain* logic — its mission, its tools, its
guardrails, its knowledge — never reimplementing the loop itself.

Per [DECISIONS.md](../../DECISIONS.md) ADR-0010, this is the direct
answer to "do not build simple role prompts": a Chief Domain Agent built
here has a `handle(Task) -> AgentResult` interface whose result carries
a full `thinking_trace` and `tool_calls` log, not just an answer string.

## Architecture

```
factories/agent-factory/
├── CONTRACT.md              language-agnostic interface spec
├── schemas/                  JSON Schemas: blueprint, task, result
├── python/
│   └── avishkar_agent/
│       ├── types.py            Task, ThinkingStep, ToolCallRecord, AgentResult
│       ├── blueprint.py        AgentBlueprint -- the declarative agent definition
│       ├── memory.py           MemoryPolicy + InMemoryMemoryPolicy (short/long/episodic/semantic)
│       ├── tools.py            ToolRegistry, Tool, MCPToolRef (typed MCP placeholder)
│       ├── thinking.py         ThinkingModel strategies (first principles, systems thinking, ...)
│       ├── guardrails.py       Guardrail, QualityGate, ApprovalGate (human-in-the-loop)
│       ├── agent.py            ChiefDomainAgent -- the plan/act/reflect reasoning loop
│       ├── orchestrator.py     Orchestrator -- single/hierarchical/swarm/conflict resolution
│       └── generator.py        scaffold_agent() -- 3 files, never "hundreds"
└── examples/
    └── quickstart.py         two toy agents + Orchestrator, all network-free
```

**How a task flows through one agent:** `ChiefDomainAgent.handle(task)`
runs every registered `Guardrail` first (a block stops the task before
any model call); then, if an `ApprovalGate` is set to `always_ask`, its
callback must allow the task; then a plan → act → reflect loop runs for
up to `blueprint.max_iterations` cycles — each cycle picks a
`ThinkingModel` (rotating through `blueprint.reasoning_strategies`),
calls the AI Router for a completion framed by that thinking step, then
reflects on whether the result is done; every `QualityGate` must pass on
the candidate result or another cycle runs (or the task ends `"failed"`
once iterations are exhausted). The full `thinking_trace` and every
`tool_calls` entry ride along in the returned `AgentResult` — see
[`examples/quickstart.py`](./examples/quickstart.py) for this running
end to end.

**How multiple agents coordinate:** `Orchestrator` holds a fixed set of
registered `ChiefDomainAgent`s and offers `.route()` (single-agent
dispatch by domain/task_type match — refuses to guess when more than one
agent could plausibly handle an unqualified task), `.delegate_team()`
(hierarchical — the same task to a named set of agents, results
collected), `.broadcast()` (swarm — same task, independent agents, for
comparison), and `.resolve_conflict()` (pluggable, named strategies over
a set of results).

## Folder Structure
See the tree above. A second-language implementation would mirror
`python/` under a sibling directory and reuse `schemas/` — see Core
Engine's README for the established pattern.

## Naming Standards
Follows [STANDARDS.md](../../STANDARDS.md) §3. Blueprint names are
kebab-case and match `agents/<name>/`. Domain modules built from
`scaffold_agent()` follow `<name>_agent.py` / `build_<name>()`.

## Interfaces

**ChiefDomainAgent** — `ChiefDomainAgent(blueprint, router, memory, tools, thinking_models, *, guardrails=(), quality_gates=(), approval_gate=None, sub_agent_router=default)`;
`.handle(task: Task) -> AgentResult`; `.route_to_sub_agent_role(task) -> str | None`.

**Orchestrator** — `Orchestrator(agents, *, shared_memory=None, event_bus=None)`;
`.route(task) -> AgentResult`; `.delegate_team(task, names) -> dict[str, AgentResult]`;
`.broadcast(task, names) -> dict[str, AgentResult]`; `.resolve_conflict(results, strategy) -> AgentResult`.

**AgentBlueprint** — `AgentBlueprint.from_dict(...)` / `.from_file(path)`; see `schemas/agent-blueprint.schema.json`.

**scaffold_agent** — `scaffold_agent(blueprint, target_dir) -> (blueprint_path, readme_path, module_path)`.

Full signatures, error conditions, and semantics: [`CONTRACT.md`](./CONTRACT.md).

## Extension Model
**Adding a new Chief Domain Agent requires zero changes to this
framework's source** (the explicit requirement behind this section): write
an `AgentBlueprint` (JSON, validated against `schemas/agent-blueprint.schema.json`),
write a small domain module that constructs a `ChiefDomainAgent` from it
— wiring real `Tool`/`MCPToolRef` entries, `Guardrail`s, `QualityGate`s,
and any domain-specific `ThinkingModel`s — and write its 30-section
README (STANDARDS.md §2.3). `scaffold_agent()` generates the three
starting files; nothing about adding a domain touches `avishkar_agent`.

Adding a new **ThinkingModel** is a new `ThinkingModel(name=..., apply=...)`
instance passed alongside `DEFAULT_THINKING_MODELS` — no framework change.
Adding a new **conflict-resolution strategy** to `Orchestrator.resolve_conflict`
means adding a named branch there (the one place in this framework where
a genuinely new *policy*, not a new *domain*, does require a source
change — tracked honestly, not hidden).

## Examples

```bash
python factories/agent-factory/examples/quickstart.py
```

Minimal single-agent call:

```python
from avishkar_agent import AgentBlueprint, ChiefDomainAgent, InMemoryMemoryPolicy, ToolRegistry, Task
from avishkar_agent.thinking import DEFAULT_THINKING_MODELS
from avishkar_router import MockProvider, RoutingPolicy, Router

router = Router([MockProvider()], RoutingPolicy(default_model="mock-fast"))
blueprint = AgentBlueprint(
    name="demo-agent", domain="Demo", version="0.1.0",
    mission="Answer demo questions.", default_model="mock-fast",
)
agent = ChiefDomainAgent(blueprint, router, InMemoryMemoryPolicy(), ToolRegistry(), DEFAULT_THINKING_MODELS)
result = agent.handle(Task(input="hello"))
print(result.status, result.output)
```

## Best Practices
- Give every agent at least one `Guardrail` before it ships — an agent
  with an empty `guardrails` tuple is one bad prompt injection away from
  doing something it shouldn't; `agents/software-ai-engineering` shows
  the pattern.
- Use `ApprovalGate(policy="always_ask", ...)` for any task class with
  real-world side effects (deploys, sends, deletes) — don't rely on
  prompting the model to "ask before doing something destructive."
- Keep `reasoning_strategies` to the thinking models a task genuinely
  benefits from — declaring all four defaults on every agent regardless
  of domain is padding, not rigor.
- Register real `Tool`s for anything actually callable today; use
  `MCPToolRef` only for integrations that genuinely wait on `mcp-factory`
  (Phase 4) — don't declare an MCP tool as a placeholder for something
  you could implement as a plain `Tool` right now.

## Anti-Patterns
- A blueprint whose `mission` is a generic role statement ("You are an
  expert X") instead of a concrete mandate — this framework's whole
  premise (ADR-0010) is that a Chief Domain Agent is a system, and a
  vague mission is the first sign it's secretly just a prompt.
- Running `scaffold_agent()` and leaving the generated README's
  `_TODO:_` placeholders unfilled — the generator produces a *starting
  point*, not a finished agent; STANDARDS.md's rule against files that
  exist without a stated purpose applies to every one of the 30 sections.
- Spawning a new top-level agent for what is actually a role within an
  existing domain — see ARCHITECTURE.md §4's absorption test, and use
  `sub_agent_roles` + `route_to_sub_agent_role` instead.
- Catching `AgentFrameworkError` broadly instead of the specific
  exception (`GuardrailBlockedError`, `NoMatchingAgentError`, ...) —
  defeats the point of a typed hierarchy, same objection as in Core
  Engine's Anti-Patterns.
- Building a second Orchestrator per product instead of registering that
  product's agents with one shared Orchestrator — the whole point of a
  platform-level Orchestrator is one coordination point, not N of them.

## Future Roadmap
- **Automatic tool selection in the reasoning loop** — v1's default
  `_act` calls the AI Router only; a registered `ToolRegistry` is
  reachable via `agent.tools.call(name, input)` for direct use today
  (by a domain module's own override, or by calling code outside
  `handle()`), but the loop doesn't yet decide *for itself* when to call
  a tool mid-reasoning. That's real agentic tool-use — deliberately
  scoped out of v1 rather than faked with a shallow heuristic.
- **Concurrent `broadcast()`/`delegate_team()`** — v1 runs candidates
  sequentially; real parallelism (asyncio or threads) once a workload
  actually needs the latency win, not preemptively.
- **Task auto-decomposition** for `delegate_team()` — v1 sends the same
  `Task` to every named agent; a coordinator that splits one task into
  per-agent sub-tasks is real hierarchical planning, deferred until a
  concrete multi-agent workflow needs it.
- **MCP tool resolution** once `mcp-factory` (Phase 4) ships — every
  `MCPToolRef` declared today becomes callable without a blueprint
  change.
- **Persistent memory backends** once `memory-factory` (Phase 5) ships —
  `MemoryPolicy` is already the seam; `InMemoryMemoryPolicy` is
  explicitly a placeholder, not the intended long-term default.
- **LangGraph-native execution** once `langgraph-factory` is scheduled
  (currently deferred, ADR-0009) — `ChiefDomainAgent`'s step shape is
  already designed to be wrappable as a LangGraph node; this item is
  wiring that wrapper, not redesigning the loop.
- **`evaluation-factory` integration** for the agent template's
  Evaluation Framework section (§16) — today an agent's quality gates are
  hand-written `QualityGate` callables; a real eval harness replaces the
  ad hoc version once that factory exists.
- A second language implementation of `CONTRACT.md`, on the same
  cadence as Core Engine's and AI Router's.
