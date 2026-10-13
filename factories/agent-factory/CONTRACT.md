# Agent Framework — Language-Agnostic Contract

The source of truth for what "Agent Framework" means, independent of
language — mirrors [`core/CONTRACT.md`](../../core/CONTRACT.md) and
[`router/CONTRACT.md`](../../router/CONTRACT.md)'s approach. Python ships
first ([`python/avishkar_agent/`](./python/avishkar_agent/));
conformance is judged against this document and
[`schemas/`](./schemas/), not against the Python source.

Per [DECISIONS.md](../../DECISIONS.md) ADR-0010, this is a **runtime**,
not a prompt library: a Chief Domain Agent is a small package (a
`AgentBlueprint` plus a domain module) that plugs into the primitives
below. Adding a new Chief Domain Agent must never require modifying this
framework's source — see §7.

---

## 1. Core types

```
Task {
  input: string                    # the task description / user request
  context: map<string, any> = {}   # caller-supplied context (files, prior results, ...)
  task_type: string | null = null  # optional hint for tool/thinking-model selection
  metadata: map<string, any> = {}  # e.g. metadata.caller for cost/audit attribution
}

ThinkingStep {
  strategy: string                 # which ThinkingModel produced this step
  content: string                  # the reasoning content itself
}

AgentResult {
  output: string
  agent_name: string
  thinking_trace: ThinkingStep[]   # ordered plan/act/reflect steps that produced `output`
  tool_calls: ToolCallRecord[]     # what was actually invoked, in order
  iterations: int                  # how many plan-act-reflect cycles ran
  status: "completed" | "blocked" | "failed"
  blocked_reason: string | null    # set when status == "blocked" (guardrail/approval)
  cost_usd: number                 # summed router cost across every model call this task made
}

ToolCallRecord { tool_name: string, input: any, output: any | null, error: string | null }
```

---

## 2. AgentBlueprint — the declarative agent definition

```
AgentBlueprint {
  name: string                     # kebab-case, matches agents/<name>/
  domain: string                   # human-readable domain, e.g. "Software & AI Engineering"
  version: string                  # semver — see SS8 Versioning
  mission: string
  reasoning_strategies: string[]   # ThinkingModel names this agent may invoke
  default_model: string            # router model_id used when a task doesn't override it
  max_iterations: int = 5          # plan-act-reflect cycle cap
  memory_policy: MemoryPolicyConfig
  tools: ToolRef[]                 # ToolRef | MCPToolRef -- see SS4
  guardrails: string[] = []        # named guardrail checks, resolved from the domain module
  quality_gates: string[] = []     # named quality-gate checks, resolved from the domain module
  sub_agent_roles: string[] = []   # internal expert roles this Chief Agent absorbs (ARCHITECTURE.md SS4)
}
```

A blueprint is data; behavior (what a guardrail/quality-gate/thinking
strategy actually *does*) lives in the domain module referenced by name,
resolved at `ChiefDomainAgent` construction — this indirection is what
lets `agent-factory` stay closed to modification while every domain
plugs in its own logic.

---

## 3. Memory — SS8 of the agent template

```
MemoryPolicy {
  remember(kind: "short_term"|"long_term"|"episodic"|"semantic", key: string, value: any) -> void
  recall(kind: "short_term"|"long_term"|"episodic"|"semantic", key: string) -> any | null
  forget(kind, key: string) -> void
}
```

v1 ships one reference implementation, `InMemoryMemoryPolicy` — process-
local, non-persistent. Real backends arrive from `memory-factory`
(Phase 5); `MemoryPolicy` is the seam that lets a persistent backend
swap in later without touching `ChiefDomainAgent`.

---

## 4. Tools — SS10, and MCP Integration Points (SS9)

```
Tool { name: string, call(input: any) -> any }

MCPToolRef { server: string, tool_name: string }
  # A DECLARED, not yet resolvable, tool reference. Calling one before
  # its `mcp/<server>` exists (Phase 4) raises MCPServerNotAvailableError
  # -- a clear, typed failure, not a crash or a silent no-op.

ToolRegistry {
  register(tool: Tool | MCPToolRef) -> void
  call(name: string, input: any) -> any
    throws ToolNotFoundError | MCPServerNotAvailableError
}
```

---

## 5. Thinking Models — SS6

```
ThinkingModel {
  name: string
  apply(task: Task, context: map<string, any>) -> ThinkingStep
}
```

Shipped reference strategies: `first_principles`, `systems_thinking`,
`scientific_method`, `decision_matrix` (a Decision Framework helper — see
SS5 of the agent template). A domain module registers additional
strategies without touching this framework.

---

## 6. ChiefDomainAgent — the reasoning loop (SS4, SS7, SS18–20)

```
ChiefDomainAgent(blueprint: AgentBlueprint, router: Router, memory: MemoryPolicy,
                 tools: ToolRegistry, thinking_models: ThinkingModel[],
                 guardrails: Guardrail[] = [], quality_gates: QualityGate[] = [],
                 approval_gate: ApprovalGate | null = null) -> ChiefDomainAgent

ChiefDomainAgent.handle(task: Task) -> AgentResult
  # 1. Guardrails run first (SS18) -- any returning a block reason stops
  #    execution before any model call; AgentResult.status = "blocked".
  # 2. If approval_gate is set and its policy is "always_ask", the gate
  #    is consulted before the first tool call that needs approval;
  #    a deny -> status = "blocked".
  # 3. Plan-Act-Reflect loop, up to blueprint.max_iterations:
  #      Plan   -> pick a ThinkingModel, produce a ThinkingStep
  #      Act    -> call router.route() for a model completion, framed by
  #                the plan step. `tools` is available to Act for direct
  #                ToolRegistry.call() use by a domain module's own
  #                override -- v1's default Act does not auto-select and
  #                invoke tools mid-loop; see README.md Future Roadmap
  #                ("automatic tool selection in the reasoning loop").
  #                Callers may also call agent.tools.call(name, input)
  #                directly, outside handle(), today.
  #      Reflect -> a ThinkingStep assessing whether the result is done;
  #                loop again if not and iterations remain
  # 4. Quality gates run on the candidate output (SS19); a failing gate
  #    either triggers another iteration (if budget remains) or marks
  #    the result "failed".
  # 5. Returns an AgentResult with the full thinking_trace and
  #    tool_calls -- the reasoning is inspectable, not just the answer.

ChiefDomainAgent.route_to_sub_agent_role(task: Task) -> string
  # Internal routing (SS24): picks which of blueprint.sub_agent_roles
  # handles `task`, if any. Absorption, not a new top-level agent
  # (ARCHITECTURE.md SS4).
```

---

## 7. Orchestrator — multi-agent, hierarchical, swarm, HITL

```
Orchestrator(agents: ChiefDomainAgent[], *, shared_memory: MemoryPolicy | null = null) -> Orchestrator

Orchestrator.route(task: Task) -> AgentResult
  # Single-agent dispatch: picks the one best-matching registered agent
  # (by declared domain/capability match against task.task_type) and
  # calls its .handle(task).
  throws NoMatchingAgentError

Orchestrator.delegate_team(task: Task, agent_names: string[]) -> map<string, AgentResult>
  # Hierarchical team: dispatches the SAME task to each named agent in
  # order, in one coordinated call -- v1 does not auto-decompose the
  # task into sub-tasks per agent (see README Future Roadmap); each
  # agent sees the same Task and the coordinator collects every result.

Orchestrator.broadcast(task: Task, agent_names: string[]) -> map<string, AgentResult>
  # Swarm: the same task to every named agent, independently, for
  # comparison/voting. v1 runs candidates sequentially (see README
  # Future Roadmap for concurrency); semantically parallel/independent.

Orchestrator.resolve_conflict(results: map<string, AgentResult>, strategy: string) -> AgentResult
  # Named conflict-resolution strategies (e.g. "first_completed",
  # "prefer_agent:<name>") -- pluggable, not hardcoded to one policy.
```

**This framework never depends on a specific product's application
logic** (ARCHITECTURE.md §1) — the Orchestrator only knows about
registered `ChiefDomainAgent` instances and named strategies.

---

## 8. Cross-cutting rules

- **Depends on Core Engine and AI Router only** (ARCHITECTURE.md §5):
  `Logger`/`EventBus` from `core/`, `Router`/`CompletionRequest` from
  `router/`. No dependency on any specific domain's content.
- **LangGraph-native compatibility (interface only, no dependency):**
  `ChiefDomainAgent`'s single reasoning-loop iteration is exposed as a
  pure function of `(state) -> state`-shaped data (a `ThinkingStep` in,
  a `ThinkingStep`/`AgentResult` out) specifically so a future
  `langgraph-factory` can wrap it as a LangGraph node without a redesign.
  No `langgraph` import exists in this framework — that dependency
  belongs to `langgraph-factory` alone, when it's scheduled (ADR-0009).
- **Zero-change extensibility:** a new Chief Domain Agent is a new
  `AgentBlueprint` + a domain module registering its tools/guardrails/
  thinking-model extensions + a 30-section README. None of that touches
  `avishkar_agent`'s own files.
