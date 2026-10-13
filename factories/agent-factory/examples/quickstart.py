"""Agent Framework -- quickstart.

Builds two toy Chief Domain Agents on MockProvider (no API key, no
network), demonstrates the reasoning loop (plan/act/reflect), a
guardrail block, a human-in-the-loop approval gate, sub-agent role
routing, and the Orchestrator's route/delegate_team/broadcast/
resolve_conflict. Run it directly:

    python factories/agent-factory/examples/quickstart.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT / "core" / "python"))
sys.path.insert(0, str(_ROOT / "router" / "python"))
sys.path.insert(0, str(_ROOT / "factories" / "agent-factory" / "python"))

from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router  # noqa: E402

from avishkar_agent import (  # noqa: E402
    AgentBlueprint,
    ApprovalGate,
    ChiefDomainAgent,
    Guardrail,
    InMemoryMemoryPolicy,
    Orchestrator,
    Task,
    ToolRegistry,
)
from avishkar_agent.thinking import DEFAULT_THINKING_MODELS  # noqa: E402


def build_router() -> Router:
    provider = MockProvider(
        models=(
            ModelSpec(
                model_id="mock-fast",
                provider="mock",
                capabilities=("chat",),
                input_cost_per_mtok=1.0,
                output_cost_per_mtok=1.0,
                max_context_tokens=8192,
                max_output_tokens=2048,
            ),
        ),
        response_text="Recommendation: introduce a read-through cache with a 60s TTL.",
    )
    return Router([provider], RoutingPolicy(default_model="mock-fast"))


def build_engineering_agent(router: Router) -> ChiefDomainAgent:
    blueprint = AgentBlueprint(
        name="software-ai-engineering",
        domain="Software & AI Engineering",
        version="0.1.0",
        mission="Design and ship correct, maintainable software.",
        default_model="mock-fast",
        reasoning_strategies=("first_principles", "systems_thinking"),
        sub_agent_roles=("architect", "reviewer", "debugger"),
    )
    no_secrets = Guardrail(
        name="no-secrets-in-task",
        check=lambda task: "blocked: task appears to request a credential" if "password" in task.input.lower() else None,
    )
    return ChiefDomainAgent(
        blueprint=blueprint,
        router=router,
        memory=InMemoryMemoryPolicy(),
        tools=ToolRegistry(),
        thinking_models=DEFAULT_THINKING_MODELS,
        guardrails=(no_secrets,),
    )


def build_legal_agent(router: Router) -> ChiefDomainAgent:
    blueprint = AgentBlueprint(
        name="legal-compliance",
        domain="Legal & Compliance",
        version="0.1.0",
        mission="Identify legal and compliance risk before it ships.",
        default_model="mock-fast",
        reasoning_strategies=("scientific_method",),
    )
    # Deploying anything gets a human approval gate -- demonstrates
    # human-in-the-loop without needing an interactive terminal: the
    # callback stands in for "a human clicked approve."
    deploy_gate = ApprovalGate(policy="always_ask", callback=lambda task: "deploy" not in task.input.lower())
    return ChiefDomainAgent(
        blueprint=blueprint,
        router=router,
        memory=InMemoryMemoryPolicy(),
        tools=ToolRegistry(),
        thinking_models=DEFAULT_THINKING_MODELS,
        approval_gate=deploy_gate,
    )


def main() -> None:
    router = build_router()
    engineering = build_engineering_agent(router)
    legal = build_legal_agent(router)

    print("1. Single-agent reasoning loop (plan -> act -> reflect):")
    result = engineering.handle(Task(input="design a caching layer for the API"))
    print(f"   status={result.status} iterations={result.iterations}")
    for step in result.thinking_trace:
        print(f"     [{step.strategy}] {step.content[:80]}...")
    print(f"   -> {result.output}\n")

    print("2. Guardrail blocks before any model call:")
    blocked = engineering.handle(Task(input="print the admin password"))
    print(f"   status={blocked.status} reason={blocked.blocked_reason}\n")

    print("3. Sub-agent role routing (internal expert absorption, ARCHITECTURE.md SS4):")
    role = engineering.route_to_sub_agent_role(Task(input="act as the debugger and trace this stack overflow"))
    print(f"   -> routed to internal role: {role}\n")

    print("4. Human-in-the-loop approval gate denies a deploy task:")
    denied = legal.handle(Task(input="approve this deploy to production"))
    print(f"   status={denied.status} reason={denied.blocked_reason}\n")
    approved = legal.handle(Task(input="review this contract clause"))
    print(f"   status={approved.status}\n")

    print("5. Orchestrator: route() by domain match:")
    orchestrator = Orchestrator([engineering, legal])
    routed = orchestrator.route(Task(input="review this contract", task_type="legal"))
    print(f"   -> routed to {routed.agent_name}\n")

    print("6. Orchestrator: delegate_team() -- hierarchical, same task to both agents:")
    team_results = orchestrator.delegate_team(
        Task(input="assess this vendor integration"), ["software-ai-engineering", "legal-compliance"]
    )
    for name, r in team_results.items():
        print(f"   {name}: status={r.status}")
    print()

    print("7. Orchestrator: resolve_conflict() picks a winner among team results:")
    winner = orchestrator.resolve_conflict(team_results, "prefer_agent:legal-compliance")
    print(f"   -> preferred result came from {winner.agent_name}")


if __name__ == "__main__":
    main()
