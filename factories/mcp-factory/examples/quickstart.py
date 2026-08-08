"""Universal Integration Framework -- quickstart.

Demonstrates the real MCPAdapter and RESTAdapter (dependency-injected
with a fake session/transport instead of a live server -- see
tests/test_mcp_adapter.py and tests/test_rest_adapter.py for the same
pattern), the UniversalToolRegistry, ToolRuntime (retries, an access-
control denial, a human-in-the-loop approval gate, memory integration),
IntegrationPlanner (capability -> best tool), the Agent Framework bridge,
and a LangGraph-shaped node -- all with no live network call and no API
key. Run it directly:

    python factories/mcp-factory/examples/quickstart.py
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT / "core" / "python"))
sys.path.insert(0, str(_ROOT / "router" / "python"))
sys.path.insert(0, str(_ROOT / "factories" / "agent-factory" / "python"))
sys.path.insert(0, str(_ROOT / "factories" / "mcp-factory" / "python"))

from avishkar_agent import ApprovalGate, InMemoryMemoryPolicy, MCPToolRef, Task  # noqa: E402
from avishkar_core import EventBus  # noqa: E402

from avishkar_integration import (  # noqa: E402
    AccessControlPolicy,
    IntegrationPlanner,
    RetryPolicy,
    SecurityPolicy,
    ToolRuntime,
    UniversalToolRegistry,
    make_tool_execution_node,
    request_capability,
    resolve_mcp_tool_ref,
)
from avishkar_integration.adapters.mcp_adapter import MCPAdapter  # noqa: E402
from avishkar_integration.adapters.rest_adapter import RESTAdapter  # noqa: E402
from avishkar_integration.types import ToolContract  # noqa: E402


def build_mcp_adapter() -> MCPAdapter:
    """A fake 'github' MCP server session, standing in for a live
    subprocess-backed MCP server -- same injection seam production code
    uses to unit test MCPAdapter (see tests/test_mcp_adapter.py).
    """

    class _FakeGithubSession:
        async def initialize(self):
            return None

        async def list_tools(self):
            tool = SimpleNamespace(
                name="create_pull_request",
                description="Open a pull request on a GitHub repository.",
                input_schema={"type": "object", "properties": {"title": {"type": "string"}}},
                output_schema=None,
            )
            return SimpleNamespace(tools=[tool])

        async def call_tool(self, name, arguments):
            content = SimpleNamespace(type="text", text=f"Opened PR #42: {arguments.get('title', '')}")
            return SimpleNamespace(is_error=False, content=[content])

    @asynccontextmanager
    async def session_provider():
        yield _FakeGithubSession()

    return MCPAdapter(session_provider=session_provider, server_name="github")


def build_rest_adapter() -> RESTAdapter:
    """A REST tool declared against a fake transport instead of a live
    HTTP endpoint -- proving the abstraction layer is real for a second,
    genuinely different protocol (ADR-0011 SS1).
    """

    def fake_weather_transport(method, url, headers, body):
        import json

        return 200, json.dumps({"temp_f": 68, "conditions": "cloudy"}).encode()

    adapter = RESTAdapter(transport=fake_weather_transport)
    adapter.register_tool(
        ToolContract(
            identity="get_weather",
            description="Get current weather for a city.",
            protocol="rest",
            input_schema={"type": "object", "properties": {"city": {"type": "string"}}},
            permissions=("weather",),
            retry_policy=RetryPolicy(max_attempts=2),
            protocol_config={"method": "GET", "url": "https://api.example.com/weather"},
        )
    )
    return adapter


def main() -> None:
    registry = UniversalToolRegistry()
    registry.register_adapter(build_mcp_adapter())
    registry.register_adapter(build_rest_adapter())

    print("1. Universal registry, two real protocols, one contract shape:")
    for contract in registry.list_tools():
        print(f"   {contract.qualified_name}: {contract.description}")
    print()

    event_bus = EventBus()
    event_bus.subscribe("integration.tool.executed", lambda e: print(f"   [event] executed: {e.payload}"))
    memory = InMemoryMemoryPolicy()
    runtime = ToolRuntime(
        registry,
        security_policies={"mcp:create_pull_request": SecurityPolicy(access_control=AccessControlPolicy(allowed_callers=("release-bot",)))},
        approval_gate=ApprovalGate(policy="always_ask", callback=lambda task: "production" not in task.input.lower()),
        memory=memory,
        event_bus=event_bus,
    )

    print("2. Execute a REST tool through the runtime (retries/metrics/memory wired):")
    result = runtime.execute("rest", "get_weather", {"city": "Paris"})
    print(f"   status={result.status} output={result.output}")
    print(f"   memory recalls last_tool_call={memory.recall('short_term', 'last_tool_call')}\n")

    print("3. Access control denies an unauthorized caller before any MCP call:")
    denied = runtime.execute("mcp", "create_pull_request", {"title": "Add caching"}, caller="random-agent")
    print(f"   status={denied.status} reason={denied.error}\n")

    print("4. Authorized caller + approval gate allowed -> MCP call proceeds:")
    allowed = runtime.execute("mcp", "create_pull_request", {"title": "Add caching"}, caller="release-bot")
    print(f"   status={allowed.status} output={allowed.output}\n")

    print("5. Approval gate blocks a 'production' deploy regardless of caller:")
    blocked = runtime.execute(
        "mcp", "create_pull_request", {"title": "deploy to production"}, caller="release-bot"
    )
    print(f"   status={blocked.status} reason={blocked.error}\n")

    print("6. IntegrationPlanner: capability -> best tool, protocol-agnostic:")
    planner = IntegrationPlanner(registry)
    plan = planner.plan("weather")
    print(f"   -> {plan.rationale}\n")

    print("7. Agent Framework bridge -- agents consume capabilities, not protocols:")
    contract = request_capability(registry, "weather")
    print(f"   request_capability('weather') -> {contract.qualified_name}")
    ref = MCPToolRef(server="github", tool_name="create_pull_request")
    resolved = resolve_mcp_tool_ref(ref, registry)
    print(f"   resolve_mcp_tool_ref(github/create_pull_request) -> {resolved.qualified_name}\n")

    print("8. LangGraph-shaped node -- a plain function of state, no langgraph import:")
    node = make_tool_execution_node(runtime, "rest", "get_weather")
    state = node({"tool_input": {"city": "London"}, "caller": "release-bot"})
    print(f"   node({{'tool_input': ...}}) -> tool_output.status={state['tool_output'].status}\n")

    print("9. Metrics collected across everything above:")
    print(f"   rest:get_weather call_count={runtime.metrics.call_count('rest:get_weather')}")
    print(f"   mcp:create_pull_request error_rate={runtime.metrics.error_rate('mcp:create_pull_request'):.2f}")


if __name__ == "__main__":
    main()
