"""Software & AI Engineering Chief Domain Agent -- quickstart.

Runs on MockProvider (no API key, no network) by default. Swap
MockProvider for AnthropicProvider and drop `model_override` to use the
committed blueprint's real default_model ("claude-opus-5") -- see
router/README.md. Run directly:

    python agents/software-ai-engineering/examples/quickstart.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT / "core" / "python"))
sys.path.insert(0, str(_ROOT / "router" / "python"))
sys.path.insert(0, str(_ROOT / "factories" / "agent-factory" / "python"))
sys.path.insert(0, str(_ROOT / "agents" / "software-ai-engineering" / "python"))

from avishkar_agent import Task  # noqa: E402
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router  # noqa: E402

from software_ai_engineering_agent import build_software_ai_engineering_agent  # noqa: E402


def main() -> None:
    provider = MockProvider(
        models=(
            ModelSpec(
                model_id="mock-fast",
                provider="mock",
                capabilities=("chat", "tools"),
                input_cost_per_mtok=1.0,
                output_cost_per_mtok=1.0,
                max_context_tokens=8192,
                max_output_tokens=2048,
            ),
        ),
        response_text=(
            "Recommendation: introduce a read-through cache in front of the "
            "pricing service with a 60s TTL and explicit invalidation on price "
            "updates, rather than a write-through cache -- price reads vastly "
            "outnumber writes, so we optimize for read latency at the cost of "
            "brief staleness."
        ),
    )
    router = Router([provider], RoutingPolicy(default_model="mock-fast"))
    agent = build_software_ai_engineering_agent(router, model_override="mock-fast")

    print("1. A normal design task runs the full reasoning loop:")
    result = agent.handle(Task(input="design a caching strategy for the pricing API"))
    print(f"   status={result.status} iterations={result.iterations} cost=${result.cost_usd:.6f}")
    for step in result.thinking_trace:
        print(f"     [{step.strategy}] {step.content[:90]}...")
    print(f"   -> {result.output}\n")

    print("2. Registered tools are real, callable code (not stubs):")
    issues = agent.tools.call("static_check", "def f():\n    print('debug')\n")
    print(f"   static_check found: {issues}")
    complexity = agent.tools.call("estimate_complexity", "if a:\n  pass\nelif b:\n  pass\n")
    print(f"   estimate_complexity: {complexity}\n")

    print("3. A declared MCP tool fails clearly, not silently, until Phase 4:")
    try:
        agent.tools.call("mcp:github/create_pull_request", {"title": "Add caching layer"})
    except Exception as exc:  # MCPServerNotAvailableError
        print(f"   -> {type(exc).__name__}: {exc}\n")

    print("4. Guardrail blocks a destructive-command request before any model call:")
    blocked = agent.handle(Task(input="run git push --force to clean up the branch"))
    print(f"   status={blocked.status} reason={blocked.blocked_reason}\n")

    print("5. Internal sub-agent role routing (absorbed roles, ARCHITECTURE.md SS4):")
    role = agent.route_to_sub_agent_role(Task(input="act as the security-auditor and check this endpoint"))
    print(f"   -> routed to internal role: {role}")


if __name__ == "__main__":
    main()
