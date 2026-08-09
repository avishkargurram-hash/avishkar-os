"""Orchestrator ("Executive Orchestrator") -- quickstart.

Builds all 10 domain Chief Domain Agents and composes them under one
real avishkar_agent.Orchestrator, then demonstrates route(),
delegate_team(), broadcast(), and resolve_conflict() -- the whole
platform, wired together, on MockProvider (no API key, no network).
Run directly:

    python agents/orchestrator/examples/quickstart.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
for rel in (
    "core/python", "router/python", "factories/agent-factory/python",
    "factories/mcp-factory/python", "factories/knowledge-factory/python",
    "factories/memory-factory/python", "factories/workflow-factory/python",
    "factories/prompt-factory/python", "factories/evaluation-factory/python",
    "factories/security-factory/python", "agents/orchestrator/python",
):
    sys.path.insert(0, str(_ROOT / rel))

from avishkar_agent import Task  # noqa: E402
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router  # noqa: E402

from orchestrator_agent import build_executive_orchestrator  # noqa: E402


def main() -> None:
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat", "tools"),
                           input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text="Here is a considered answer from this domain's perspective.",
    )
    router = Router([provider], RoutingPolicy(default_model="mock-fast"))
    orchestrator = build_executive_orchestrator(router, model_override="mock-fast")

    print(f"1. All {len(orchestrator.list_agents())} domain agents registered:")
    for name in orchestrator.list_agents():
        print(f"   - {name}")
    print()

    print("2. route() -- single-agent dispatch by exact name:")
    result = orchestrator.route(Task(input="What's a healthy debt-to-equity ratio?", task_type="finance-economics"))
    print(f"   status={result.status} agent={result.agent_name}\n")

    print("3. delegate_team() -- one task, two agents, both perspectives:")
    team_results = orchestrator.delegate_team(
        Task(input="Review this new product idea."),
        ["legal-compliance", "finance-economics"],
    )
    for name, r in team_results.items():
        print(f"   {name}: status={r.status}")
    print()

    print("4. broadcast() -- swarm comparison across agents:")
    broadcast_results = orchestrator.broadcast(
        Task(input="What do you think of this pitch?"),
        ["creative-media", "startup-business-product"],
    )
    print(f"   {len(broadcast_results)} independent responses collected\n")

    print("5. resolve_conflict() -- picking a winner among candidates:")
    resolved = orchestrator.resolve_conflict(broadcast_results, "first_completed")
    print(f"   resolved to: {resolved.agent_name}")


if __name__ == "__main__":
    main()
