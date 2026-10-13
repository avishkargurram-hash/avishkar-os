# Universal Integration Framework — Language-Agnostic Contract

The source of truth for what this framework means, independent of
language — mirrors [`core/CONTRACT.md`](../../core/CONTRACT.md),
[`router/CONTRACT.md`](../../router/CONTRACT.md), and
[`agent-factory/CONTRACT.md`](../agent-factory/CONTRACT.md)'s approach.
Python ships first ([`python/avishkar_integration/`](./python/avishkar_integration/));
conformance is judged against this document and
[`schemas/`](./schemas/), not against the Python source.

Per [DECISIONS.md](../../DECISIONS.md) ADR-0011: this framework keeps the
`mcp-factory` name and slot but is scoped as a **protocol-agnostic
integration platform** with MCP as its first, not only, implementation —
structurally identical to how AI Router is provider-agnostic with
`AnthropicProvider` as its first adapter (ADR-0008/Phase 2 precedent).

---

## 1. Core types

```
ToolContract {
  identity: string                  # unique within its protocol
  description: string
  protocol: string                  # "mcp" | "rest" | ... -- see SS3
  input_schema: object               # JSON Schema
  output_schema: object | null       # JSON Schema
  permissions: string[] = []         # capability/permission tags -- also
                                      # used for capability lookup, SS7
  auth_requirement: string = "none"  # "none" | "api_key" | "oauth2" | "mcp_session" | ...
  rate_limit: RateLimit | null
  timeout_seconds: number = 30.0
  retry_policy: RetryPolicy
  error_handling: string = "return_error_result"  # | "raise"
  version: string = "1.0.0"
  health_status: string = "unknown"  # declared default; LIVE status is
                                      # tracked by the registry (SS4), not
                                      # mutated on this frozen record
  audit: AuditInfo
  protocol_config: map<string, any> = {}  # protocol-specific extras
                                            # (e.g. REST method/url template)
}

RateLimit { requests_per_minute: int }
RetryPolicy { max_attempts: int = 1, backoff_seconds: number = 0.0 }
AuditInfo { created_by: string = "unknown", created_at: string = "" }

ToolExecutionRequest { input: any, caller: string | null = null, metadata: map<string, any> = {} }

ToolExecutionResult {
  tool_identity: string
  protocol: string
  status: "success" | "error" | "timeout" | "denied"
  output: any | null
  error: string | null
  latency_ms: number
  attempts: int
}
```

**Design choice, stated explicitly:** live/mutable state (health,
invocation audit log, metrics) is deliberately kept OFF `ToolContract` —
a contract is a frozen declaration, the same choice `router/CONTRACT.md`
made for `ModelSpec` vs. `CostTracker`. Live state lives in the registry
and runtime, never on the immutable record.

---

## 2. ProtocolAdapter — the abstraction layer (SS1 of the requirement list)

```
ProtocolAdapter {
  protocol_name: string
  discover_tools() -> ToolContract[]
  invoke(contract: ToolContract, request: ToolExecutionRequest) -> ToolExecutionResult
  health_check() -> "healthy" | "unhealthy"   # default impl: discover_tools() succeeds -> healthy
}
```

Any protocol — MCP, REST, GraphQL, a Python SDK, a CLI, a database, a
filesystem, a webhook receiver, or a protocol that doesn't exist yet —
implements exactly this interface. `Router`, `avishkar_agent`, and every
other consumer in this platform depend on `ProtocolAdapter`, never on a
concrete adapter class — the same rule Router's `ModelProvider` and
Agent Framework's `ChiefDomainAgent` already establish.

**Shipped in v1:** `MCPAdapter` (real, built on the official `mcp` SDK)
and `RESTAdapter` (real, stdlib `urllib`-only). GraphQL, Python SDK, CLI,
Database, Filesystem, and Webhook adapters are documented extension
points (README.md Extension Guide) — not scaffolded stub files, per the
explicit instruction against placeholder files.

---

## 3. UniversalToolRegistry

```
UniversalToolRegistry.register_adapter(adapter: ProtocolAdapter) -> void
  throws DuplicateAdapterError   # same protocol_name registered twice
  # Calls adapter.discover_tools() and registers every returned contract.

UniversalToolRegistry.register_tool(contract: ToolContract) -> void
  # Direct registration, for a protocol adapter that discovers tools
  # lazily or for hand-declared contracts (e.g. REST tools -- SS "REST
  # tools are declared, not discovered").

UniversalToolRegistry.get(protocol: string, identity: string) -> ToolContract
  throws ToolNotFoundError

UniversalToolRegistry.get_adapter(protocol: string) -> ProtocolAdapter
  throws ProtocolNotRegisteredError

UniversalToolRegistry.list_tools(protocol: string | null = null) -> ToolContract[]

UniversalToolRegistry.find_by_capability(capability: string) -> ToolContract[]
  # Matches contracts whose `permissions` tags OR identity/description
  # text contain `capability` (case-insensitive substring) -- an honest,
  # simple matcher, not a claimed semantic search. See SS7.

UniversalToolRegistry.health_check_all() -> map<string, string>
  # Re-runs every registered adapter's health_check() and updates live
  # per-tool health (keyed "protocol:identity").

UniversalToolRegistry.get_health(protocol: string, identity: string) -> string
```

---

## 4. Integration Policies (SS5 of the requirement list)

```
AccessControlPolicy {
  allowed_callers: string[] | null = null   # null = allow all
  denied_callers: string[] = []
  is_allowed(caller: string | null) -> bool
}

SecurityPolicy {
  trust_level: "trusted" | "untrusted" = "untrusted"
  require_sandbox: bool = false
  access_control: AccessControlPolicy
}
```

**Sandboxing, stated honestly:** v1 has no real sandbox execution
environment. `require_sandbox=true` on an untrusted tool causes
`ToolRuntime.execute()` to return `status="denied"` rather than silently
running unsandboxed — refusing is the safe default until a real sandbox
exists (README.md Future Roadmap), not a claim that sandboxing is
implemented.

**Approval gates reuse `avishkar_agent.ApprovalGate`** (ADR-0011 §7) —
the same human-in-the-loop primitive Agent Framework already ships,
applied at the tool-execution boundary via a synthesized `Task`
representing the pending call, rather than a duplicate class.

---

## 5. ToolRuntime (SS4 of the requirement list)

```
ToolRuntime(registry: UniversalToolRegistry, *,
            security_policies: map<string, SecurityPolicy> = {},
            approval_gate: ApprovalGate | null = null,
            memory: MemoryPolicy | null = null,
            event_bus: EventBus | null = null,
            metrics: MetricsCollector | null = null) -> ToolRuntime

ToolRuntime.execute(protocol: string, identity: string, input: any, *,
                     caller: string | null = null,
                     metadata: map<string, any> = {}) -> ToolExecutionResult
  throws ToolNotFoundError | ProtocolNotRegisteredError
  # 1. Look up the ToolContract (raises if unknown -- a caller bug, not
  #    a runtime business outcome).
  # 2. Access-control / sandbox / approval-gate checks -- a business
  #    denial returns status="denied" in the result, never raises.
  # 3. Retries up to contract.retry_policy.max_attempts, invoking the
  #    matching ProtocolAdapter each attempt.
  # 4. Every attempt logs via Core Engine's Logger, publishes
  #    "integration.tool.executed" via EventBus if set, records into
  #    MetricsCollector (count/error-rate/latency/cost), and -- if a
  #    MemoryPolicy is set -- writes an episodic record of the call and
  #    updates the "last_tool_call" short_term key.
```

---

## 6. IntegrationPlanner — AI Router Integration (SS8)

```
ExecutionPlan { tool_contract: ToolContract, model_id: string | null, rationale: string }

IntegrationPlanner(registry: UniversalToolRegistry, router: Router | null = null) -> IntegrationPlanner

IntegrationPlanner.plan(capability: string, *, task_type: string | null = null) -> ExecutionPlan
  throws NoMatchingToolError
  # "Best tool / best protocol / best execution path": picks a healthy
  # matching ToolContract over an unhealthy one when both exist for the
  # same capability; "best model" is explicitly delegated to the already-
  # built AI Router (Phase 2), not reinvented here.
```

---

## 7. Agent Integration (SS7)

```
resolve_mcp_tool_ref(ref: avishkar_agent.MCPToolRef, registry: UniversalToolRegistry) -> ToolContract
  throws ToolNotFoundError
  # Resolves an agent-declared MCPToolRef (agent-factory CONTRACT.md SS4)
  # against a real registry -- the seam agent-factory always intended
  # (see ADR-0011 §7), with no change to agent-factory's own source.

request_capability(registry: UniversalToolRegistry, capability: string) -> ToolContract
  throws NoMatchingToolError
  # "Agents request capabilities, not implementations": the entry point
  # a Chief Domain Agent's domain module calls instead of naming a
  # specific protocol/tool.
```

---

## 8. LangGraph-shaped nodes (SS9)

```
# All of the following return Callable[[State], PartialState] --
# LangGraph's own node contract -- with NO import of the `langgraph`
# package anywhere in this framework (ADR-0011 §2). A caller wires the
# returned function into their own StateGraph.

make_tool_execution_node(runtime, protocol, identity, *, input_key, output_key) -> NodeFn
make_mcp_call_node(runtime, identity, **kwargs) -> NodeFn        # = make_tool_execution_node(..., "mcp", ...)
make_rest_call_node(runtime, identity, **kwargs) -> NodeFn       # = make_tool_execution_node(..., "rest", ...)
make_retry_node(inner: NodeFn, *, max_attempts, is_success) -> NodeFn
make_approval_node(approval_gate, *, task_factory) -> NodeFn
make_logging_node(logger, *, message) -> NodeFn
```

---

## Cross-cutting rules

- **Depends on Core Engine, AI Router, and Agent Framework**
  (`core/`, `router/`, `agent-factory` — for `agent_bridge.py` and
  `ApprovalGate` reuse only). No other module in this framework imports
  `avishkar_agent`.
- **Adding a new protocol adapter never changes this framework's core**
  (`types.py`, `protocol.py`, `registry.py`, `runtime.py`) — only a new
  file under `adapters/` implementing `ProtocolAdapter`, exactly Agent
  Framework's zero-change extensibility rule applied to protocols.
- **No component depends on another component's concrete class** — only
  on `ProtocolAdapter`, never on `MCPAdapter`/`RESTAdapter` by name,
  outside the adapters themselves.
