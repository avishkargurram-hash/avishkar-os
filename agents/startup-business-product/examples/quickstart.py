"""Startup, Business & Product Chief Domain Agent -- quickstart.

Runs on MockProvider (no API key, no network). Run directly:

    python agents/startup-business-product/examples/quickstart.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
for rel in (
    "core/python", "router/python", "factories/agent-factory/python",
    "factories/memory-factory/python", "factories/knowledge-factory/python",
    "factories/evaluation-factory/python", "factories/prompt-factory/python",
    "factories/workflow-factory/python", "factories/mcp-factory/python",
    "factories/security-factory/python", "agents/startup-business-product/python",
):
    sys.path.insert(0, str(_ROOT / rel))

from avishkar_agent import Task  # noqa: E402
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router  # noqa: E402

from startup_business_product_agent import build_startup_business_product_agent  # noqa: E402


def main() -> None:
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat", "tools"),
                           input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text="Here's a structured PRD outline. Not financial advice -- consult your own judgment on funding.",
    )
    router = Router([provider], RoutingPolicy(default_model="mock-fast"))
    agent = build_startup_business_product_agent(router, model_override="mock-fast")

    print("1. Ordinary product-strategy question:")
    result = agent.handle(Task(input="Help me structure a PRD for my new product."))
    print(f"   status={result.status} output={result.output}\n")

    print("2. Pitch clarity check (direct tool call):")
    pitch = "The problem is churn. Our solution is proactive outreach. The market is large. Our ask is $2M."
    print(f"   sections present: {agent.tools.call('score_pitch_clarity', pitch)}\n")

    print("3. Market size classification (direct tool call):")
    print(f"   'a billion-dollar global market' -> {agent.tools.call('classify_market_size', 'a billion-dollar global market')}\n")

    print("4. Guardrail blocking a binding-commitment request:")
    blocked = agent.handle(Task(input="Please sign this term sheet on my behalf"))
    print(f"   status={blocked.status} reason={blocked.blocked_reason}\n")

    print("5. Sub-agent routing:")
    role = agent.route_to_sub_agent_role(Task(input="Can the market-analyst review this?"))
    print(f"   routed to: {role}")


if __name__ == "__main__":
    main()
