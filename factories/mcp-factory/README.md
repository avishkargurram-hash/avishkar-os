# Universal Integration Framework

## Vision
Every capability outside this platform's own process — a GitHub API, a
weather service, a database, an MCP server, a future protocol nobody has
invented yet — should reach a Chief Domain Agent through one contract,
not a different bespoke integration per protocol. Universal Integration
Framework is that contract: a protocol-agnostic tool platform with MCP
as its first, production-quality implementation — never only an MCP
wrapper (per the Master Build Directive's explicit instruction). Per
[DECISIONS.md](../../DECISIONS.md) ADR-0011, this keeps the `mcp-factory`
name and slot from ARCHITECTURE.md's factory table, with its scope
deepened the same way AI Router is provider-agnostic with
`AnthropicProvider` as its first adapter (Phase 2 precedent).

## Architecture

```
factories/mcp-factory/
├── CONTRACT.md              language-agnostic interface spec (source of truth)
├── schemas/                  JSON Schemas: tool contract, execution request/result
├── python/
│   └── avishkar_integration/
│       ├── types.py             ToolContract (12-field universal contract), execution types
│       ├── protocol.py          ProtocolAdapter -- the Protocol Abstraction Layer
│       ├── registry.py          UniversalToolRegistry -- every tool, every protocol, one lookup
│       ├── policies.py          AccessControlPolicy, SecurityPolicy (trust level, sandboxing)
│       ├── metrics.py           MetricsCollector -- calls, errors, latency, cost
│       ├── runtime.py           ToolRuntime -- execute/retry/log/meter/approve/remember
│       ├── planner.py           IntegrationPlanner -- AI Router integration (best tool/model)
│       ├── agent_bridge.py      Agent Framework integration (capabilities, not protocols)
│       ├── langgraph_nodes.py   LangGraph-shaped reusable nodes (no langgraph dependency)
│       └── adapters/
│           ├── mcp_adapter.py    MCPAdapter -- real, built on the official `mcp` SDK
│           └── rest_adapter.py   RESTAdapter -- real, stdlib `urllib` only
└── examples/
    └── quickstart.py         all of the above, end to end, no live network
```

**Request flow:** a caller (a Chief Domain Agent, a workflow, a
LangGraph node) calls `ToolRuntime.execute(protocol, identity, input, ...)`
→ the runtime looks up the `ToolContract` in the `UniversalToolRegistry`
→ runs access-control, sandbox-trust, and human-in-the-loop approval
checks (any denial returns immediately, no protocol call made) → invokes
the matching `ProtocolAdapter`, retrying per the contract's
`RetryPolicy` → logs, publishes `integration.tool.*` events, records
`MetricsCollector` stats, and — if a `MemoryPolicy` is configured — writes
an episodic record of the call. See
[`examples/quickstart.py`](./examples/quickstart.py) for every one of
these running against two real, different protocols with no live network
call.

## Contracts
See [`CONTRACT.md`](./CONTRACT.md) for the full language-agnostic
specification, and [`schemas/`](./schemas/) for the JSON Schemas
(`ToolContract`, `ToolExecutionRequest`/`Result`). The 12-field universal
tool contract (identity, description, input/output schema, permissions,
auth requirement, rate limit, timeout, retry policy, error handling,
version, health status, audit info) is the one shape every protocol
adapter publishes — a caller never needs to know whether a given
capability is MCP, REST, or something else.

## Interfaces

**ProtocolAdapter** (implement to add a protocol) — `.protocol_name`,
`.discover_tools() -> tuple[ToolContract, ...]`,
`.invoke(contract, request) -> ToolExecutionResult`, `.health_check()`.

**UniversalToolRegistry** — `.register_adapter(adapter)`,
`.register_tool(contract)`, `.get(protocol, identity)`,
`.find_by_capability(capability)`, `.health_check_all()`.

**ToolRuntime** — `ToolRuntime(registry, *, security_policies=, approval_gate=, memory=, event_bus=, metrics=)`;
`.execute(protocol, identity, input, *, caller=, metadata=) -> ToolExecutionResult`.

**IntegrationPlanner** — `.plan(capability, *, task_type=) -> ExecutionPlan`.

**Agent Framework bridge** — `resolve_mcp_tool_ref(ref, registry)`,
`request_capability(registry, capability)`.

**LangGraph-shaped nodes** — `make_tool_execution_node`, `make_mcp_call_node`,
`make_rest_call_node`, `make_retry_node`, `make_approval_node`, `make_logging_node`
— every one returns a plain `Callable[[State], PartialState]`.

Full signatures and error conditions: [`CONTRACT.md`](./CONTRACT.md).

## Folder Structure
See the Architecture tree above. `adapters/` is the only directory a new
protocol implementation touches — see Extension Guide.

## Naming Standards
Follows [STANDARDS.md](../../STANDARDS.md) §3. Adapter files are named
`<protocol>_adapter.py`; the class is `<Protocol>Adapter`. `ToolContract`
identities are the protocol's own naming (an MCP tool's `name`, a REST
endpoint's logical name) — this framework never renames them.

## Examples

```bash
python factories/mcp-factory/examples/quickstart.py
```

Minimal: register a protocol, execute a tool.

```python
from avishkar_integration import ToolRuntime, UniversalToolRegistry
from avishkar_integration.adapters.rest_adapter import RESTAdapter
from avishkar_integration.types import ToolContract

adapter = RESTAdapter()
adapter.register_tool(ToolContract(
    identity="get_weather", description="...", protocol="rest",
    input_schema={"type": "object"},
    protocol_config={"method": "GET", "url": "https://api.example.com/weather"},
))
registry = UniversalToolRegistry()
registry.register_adapter(adapter)
runtime = ToolRuntime(registry)
result = runtime.execute("rest", "get_weather", {"city": "Paris"})
```

## Testing Strategy
70 unit tests, all passing, organized per module
(`types`, `protocol` via a `FakeAdapter` fixture, `registry`, `policies`,
`metrics`, `runtime`, `planner`, `agent_bridge`, `langgraph_nodes`,
`mcp_adapter`, `rest_adapter`). Both real adapters are tested via
**dependency injection**, not a live network call or subprocess — MCP
via an injected `session_provider` (a fake async context manager
matching the official SDK's `ClientSession` shape), REST via an injected
`transport` function — the same seam pattern `AnthropicProvider`
established in `router/` (Phase 2). Two real bugs were caught by actually
running [`examples/quickstart.py`](./examples/quickstart.py), not staged
for demonstration: a `protocol` field mismatch between an adapter's
`protocol_name` and its own discovered contracts (now a hard
`ProtocolMismatchError` at registration time) and an approval-gate
callback unable to see the actual tool-call input (now embedded directly
in the synthesized `Task.input`). Both are regression-tested.

## Best Practices
- Give every tool a real `RetryPolicy` and `timeout_seconds` — the
  defaults (`max_attempts=1`, `30s`) are safe but rarely optimal; set
  them per tool based on how expensive a retry actually is.
- Attribute every `ToolRuntime.execute()` call with `caller=` — both
  `AccessControlPolicy` and per-caller metrics depend on it being set
  consistently, the same discipline `router/README.md` asks for cost
  attribution.
- Use `IntegrationPlanner`/`request_capability` from agent and workflow
  code instead of naming a protocol directly — that's the whole point of
  "agents request capabilities, not implementations" (CONTRACT.md §7).
- Reach for `SecurityPolicy(trust_level="untrusted", require_sandbox=True)`
  on any tool you haven't personally reviewed — v1 denies rather than
  runs it unsandboxed (see Limitations), which is the safe failure mode.

## Extension Guide
Adding a new protocol never touches `types.py`, `protocol.py`,
`registry.py`, `runtime.py`, `planner.py`, `agent_bridge.py`, or
`langgraph_nodes.py` — only a new file under `adapters/` implementing
`ProtocolAdapter`. Documented, not-yet-built extension points (no
placeholder files, per the explicit instruction against them):

| Protocol | What it would need |
|---|---|
| GraphQL | A `GraphQLAdapter` sending queries/mutations per `ToolContract.protocol_config` (query template, variables mapping) — same shape as `RESTAdapter`, different wire format. |
| Python SDKs | A `SDKAdapter` wrapping an installed Python package's functions as tools — `protocol_config` names the module/function; discovery could introspect a package's public callables. |
| CLI | A `CLIAdapter` running a subprocess per invocation, `protocol_config` holding the command template; needs careful argument-escaping (see Security Policies above). |
| Databases | A `DatabaseAdapter` running parameterized queries declared per tool (never raw caller-supplied SQL) — `protocol_config` holds the connection string reference and query template. |
| Filesystems | A `FilesystemAdapter` scoped to a fixed root, with the same path-traversal defense the `claude-api` skill's text-editor tool guidance describes. |
| Webhooks | A `WebhookAdapter` for outbound event delivery — `invoke()` posts to a configured endpoint; `discover_tools()` would be a fixed, hand-declared list, same as REST. |

Each becomes real by: (1) implementing `ProtocolAdapter`, (2) publishing
`ToolContract`s with `protocol_config` fields specific to that protocol,
(3) unit tests using the same dependency-injection seam `MCPAdapter`/
`RESTAdapter` establish (never a live external call in the test suite).

## Anti-Patterns
- Catching a protocol adapter's vendor-specific exception outside the
  adapter itself (e.g. `except mcp.McpError` in calling code) — defeats
  the normalized `ProtocolInvocationError` hierarchy this framework
  exists to provide; catch `ProtocolInvocationError` (or let `ToolRuntime`
  handle it, which it already does) instead.
- Constructing an MCP/REST client directly inside a Chief Domain Agent
  or workflow instead of going through `ToolRuntime` — reintroduces the
  per-caller protocol coupling this framework exists to remove, the same
  objection `router/README.md` makes about bypassing `Router`.
- Setting `SecurityPolicy(require_sandbox=True)` and then being surprised
  every call to that tool is denied — v1 has no real sandbox (see
  Limitations); that combination is a deliberate refusal, not a bug to
  work around by lowering the trust level just to make it run.
- Declaring a REST tool's `url` as a template with caller-supplied path
  segments interpolated unsanitized — the same path-traversal/injection
  discipline `claude-api`'s tool-use guidance applies to filesystem and
  bash tools applies here too.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `ProtocolMismatchError` at `register_adapter()` | An adapter's `discover_tools()` returned a `ToolContract` whose `.protocol` doesn't equal the adapter's own `protocol_name` — a copy-paste bug in a new adapter. |
| `ToolNotFoundError` | The `protocol:identity` pair isn't registered — check `registry.list_tools()`, and that the adapter was actually registered (`register_adapter`, not just constructed). |
| A tool call always returns `status="denied"` with no obvious reason | Check `SecurityPolicy.require_sandbox` first (v1 always denies untrusted+sandboxed tools — see Limitations) before assuming `AccessControlPolicy` is misconfigured. |
| An `ApprovalGate` callback never seems to see the real call arguments | Make sure you're reading `task.input` (a formatted string including the arguments) or `task.context["tool_input"]` (the raw value) — see the regression test in `test_runtime.py` for the exact shape. |
| `MCPAdapter()` raises `ImportError` | The `mcp` package isn't installed — `pip install mcp` or the `avishkar-integration[mcp]` extra. |
| `MCPAdapter` calls hang or are slow | Each `discover_tools()`/`invoke()` call opens a fresh subprocess + session (`asyncio.run()` per call, v1 has no session pooling) — see Future Roadmap. |

## Limitations
Stated honestly, per STANDARDS.md's rule that this section must be true:

- **No real sandboxing.** `SecurityPolicy(require_sandbox=True)` denies
  execution rather than actually isolating it — v1 has no container or
  restricted-subprocess runtime. Denying is the safe default; it is not
  the same as sandboxing.
- **No session pooling for MCP.** Every `discover_tools()`/`invoke()`
  call opens a fresh subprocess and session via `asyncio.run()` — correct
  but not efficient for high-frequency calls.
- **Rate limits are declared, not enforced.** `ToolContract.rate_limit`
  exists in the contract; `ToolRuntime` does not yet throttle calls
  against it.
- **Two protocol adapters exist** (MCP, REST); GraphQL, Python SDK, CLI,
  Database, Filesystem, and Webhook are documented extension points with
  no code — see Extension Guide.
- **No live MCP server or REST endpoint was exercised.** Every test and
  the quickstart example use dependency-injected fakes (a fake MCP
  session, a fake HTTP transport) — the same constraint `router/README.md`
  states for `AnthropicProvider`, for the same reason (no network access
  in the environment this framework was built in).

## Future Roadmap
- **MCP session pooling** — v1 opens a new stdio subprocess + session
  per `discover_tools()`/`invoke()` call; a persistent session across
  calls is a real efficiency win once a workload needs it.
- **Real sandboxed execution** for untrusted tools — v1's
  `require_sandbox=True` denies rather than fakes isolation (see
  Limitations); a real sandbox (subprocess with restricted permissions,
  or a container) is future work, not a broken promise today.
- **GraphQL, Python SDK, CLI, Database, Filesystem, Webhook adapters** —
  see the Extension Guide table above; built when a real product needs
  one, not speculatively.
- **`evaluation-factory` integration** for tool-quality scoring, mirroring
  Agent Framework's same open item.
- **Rate limiting enforcement** — `ToolContract.rate_limit` is declared
  today but not yet enforced by `ToolRuntime`; a token-bucket limiter is
  the natural next increment.
- A second language implementation of `CONTRACT.md`, on the same cadence
  as Core Engine's, AI Router's, and Agent Framework's.

---

## How this integrates with Core Engine, AI Router, and Agent Framework

- **Core Engine** (`core/`): `ToolRuntime` and `UniversalToolRegistry`
  use `Logger` for every registration/execution/denial and `EventBus`
  for `integration.tool.executed`/`.denied` events — the same
  structured-logging and pub/sub discipline every framework in this
  platform shares. No other Core Engine dependency.
- **AI Router** (`router/`, Phase 2): `IntegrationPlanner` optionally
  takes a `Router` instance and delegates "best model" selection to it
  entirely — this framework never reimplements model routing, it only
  adds "best tool" and "best protocol" on top, then hands off. A single
  `ExecutionPlan` can therefore carry both a chosen tool and a chosen
  model for one task.
- **Agent Framework** (`factories/agent-factory/`, Phase 3):
  `agent_bridge.py` is a new *consumer* of `agent-factory`'s already-
  public `MCPToolRef` type — `resolve_mcp_tool_ref()` resolves an
  agent-declared placeholder against a real registry, and
  `request_capability()` is the "agents request capabilities, not
  implementations" entry point a Chief Domain Agent's domain module can
  call instead of naming a protocol. **`agent-factory`'s own source is
  unmodified** — Phase 3's lock stands; wiring a specific Chief Domain
  Agent's `ToolRegistry` to delegate through this bridge is a small,
  deliberate change left to that agent's own domain module (e.g.
  `agents/software-ai-engineering/python/software_ai_engineering_agent.py`'s
  `MCPToolRef` entries resolve here once a real MCP server exists to
  point at), not done speculatively in this commit. `ToolRuntime` also
  directly reuses `avishkar_agent.ApprovalGate` and `MemoryPolicy` rather
  than duplicating either concept — one human-in-the-loop primitive and
  one memory contract, shared across both frameworks.
