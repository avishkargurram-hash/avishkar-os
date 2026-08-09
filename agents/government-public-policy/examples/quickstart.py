"""Government & Public Policy Chief Domain Agent -- quickstart.

Runs on MockProvider (no API key, no network). Run directly:

    python agents/government-public-policy/examples/quickstart.py
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
    "factories/security-factory/python", "agents/government-public-policy/python",
):
    sys.path.insert(0, str(_ROOT / rel))

from avishkar_agent import Task  # noqa: E402
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router  # noqa: E402

from government_public_policy_agent import build_government_public_policy_agent  # noqa: E402


def main() -> None:
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat", "tools"),
                           input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text="Submit input through the agency's official public comment channel.",
    )
    router = Router([provider], RoutingPolicy(default_model="mock-fast"))
    agent = build_government_public_policy_agent(router, model_override="mock-fast")

    print("1. Ordinary policy question:")
    result = agent.handle(Task(input="Summarize how this policy proposal would be implemented."))
    print(f"   status={result.status} output={result.output}\n")

    print("2. Policy structure check (direct tool call):")
    proposal = "The objective is reducing emissions. Stakeholders include manufacturers. Budget impact is $5M."
    print(f"   sections present: {agent.tools.call('check_policy_structure', proposal)}\n")

    print("3. Regulatory scope classification (direct tool call):")
    print(f"   'a federal regulation from Congress' -> {agent.tools.call('classify_regulatory_scope', 'a federal regulation from Congress')}\n")

    print("4. Guardrail blocking a binding-ruling request:")
    blocked = agent.handle(Task(input="Please issue an official ruling on this matter"))
    print(f"   status={blocked.status} reason={blocked.blocked_reason}\n")

    print("5. Sub-agent routing:")
    role = agent.route_to_sub_agent_role(Task(input="Can the policy-analyst review this?"))
    print(f"   routed to: {role}")


if __name__ == "__main__":
    main()
