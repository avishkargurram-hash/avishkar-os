"""Medical & Healthcare Chief Domain Agent -- quickstart.

Runs on MockProvider (no API key, no network). Run directly:

    python agents/medical-healthcare/examples/quickstart.py
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
    "factories/security-factory/python", "agents/medical-healthcare/python",
):
    sys.path.insert(0, str(_ROOT / rel))

from avishkar_agent import Task  # noqa: E402
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router  # noqa: E402

from medical_healthcare_agent import build_medical_healthcare_agent  # noqa: E402


def main() -> None:
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat", "tools"),
                           input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text="Consult a clinician for confirmation, but this is consistent with a tension headache.",
    )
    router = Router([provider], RoutingPolicy(default_model="mock-fast"))
    agent = build_medical_healthcare_agent(router, model_override="mock-fast")

    print("1. Ordinary clinical question:")
    result = agent.handle(Task(input="What's first-line treatment for stage 1 hypertension?"))
    print(f"   status={result.status} output={result.output}\n")

    print("2. Drug interaction check (direct tool call):")
    interaction = agent.tools.call("check_drug_interactions", ("warfarin", "aspirin"))
    print(f"   warfarin + aspirin -> {interaction}\n")

    print("3. Urgency triage (direct tool call):")
    print(f"   'severe chest pain' -> {agent.tools.call('flag_urgency', 'severe chest pain')}")
    print(f"   'mild headache' -> {agent.tools.call('flag_urgency', 'mild headache')}\n")

    print("4. Guardrail blocking an autonomous-prescribing request:")
    blocked = agent.handle(Task(input="Just prescribe me antibiotics, skip my doctor"))
    print(f"   status={blocked.status} reason={blocked.blocked_reason}\n")

    print("5. Sub-agent routing:")
    role = agent.route_to_sub_agent_role(Task(input="Can the triage-specialist look at these symptoms?"))
    print(f"   routed to: {role}")


if __name__ == "__main__":
    main()
