"""Finance & Economics Chief Domain Agent -- quickstart.

Runs on MockProvider (no API key, no network). Run directly:

    python agents/finance-economics/examples/quickstart.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
for rel in (
    "core/python", "router/python", "factories/agent-factory/python",
    "factories/memory-factory/python", "factories/knowledge-factory/python",
    "factories/evaluation-factory/python", "factories/prompt-factory/python",
    "factories/workflow-factory/python", "factories/mcp-factory/python",
    "factories/security-factory/python", "agents/finance-economics/python",
):
    sys.path.insert(0, str(_ROOT / rel))

from avishkar_agent import Task  # noqa: E402
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router  # noqa: E402

from finance_economics_agent import build_finance_economics_agent  # noqa: E402


def main() -> None:
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat", "tools"),
                           input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text="This is not investment advice -- consult a financial advisor before acting.",
    )
    router = Router([provider], RoutingPolicy(default_model="mock-fast"))

    with tempfile.TemporaryDirectory() as tmp:
        agent = build_finance_economics_agent(router, model_override="mock-fast", memory_root_dir=Path(tmp))

        print("1. Ordinary finance question:")
        result = agent.handle(Task(input="What's a healthy debt-to-equity ratio?"))
        print(f"   status={result.status} output={result.output}\n")

        print("2. Debt-to-equity calculation (direct tool call):")
        print(f"   (200, 100) -> {agent.tools.call('calculate_debt_to_equity_ratio', (200.0, 100.0))}\n")

        print("3. Risk classification (direct tool call):")
        print(f"   30% volatility -> {agent.tools.call('classify_risk_level', 30.0)}\n")

        print("4. Guardrail blocking a trade-execution request:")
        blocked = agent.handle(Task(input="Please execute this trade immediately"))
        print(f"   status={blocked.status} reason={blocked.blocked_reason}\n")

        print("5. Sub-agent routing:")
        role = agent.route_to_sub_agent_role(Task(input="Can the risk-modeler review this?"))
        print(f"   routed to: {role}")


if __name__ == "__main__":
    main()
