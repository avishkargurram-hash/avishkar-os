"""Education & Knowledge Chief Domain Agent -- quickstart.

Runs on MockProvider (no API key, no network). Run directly:

    python agents/education-knowledge/examples/quickstart.py
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
    "factories/security-factory/python", "agents/education-knowledge/python",
):
    sys.path.insert(0, str(_ROOT / rel))

from avishkar_agent import Task  # noqa: E402
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router  # noqa: E402

from education_knowledge_agent import build_education_knowledge_agent  # noqa: E402


def main() -> None:
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat", "tools"),
                           input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text="Have your instructor confirm the final rubric before grading.",
    )
    router = Router([provider], RoutingPolicy(default_model="mock-fast"))

    with tempfile.TemporaryDirectory() as tmp:
        agent = build_education_knowledge_agent(router, model_override="mock-fast", memory_root_dir=Path(tmp))

        print("1. Ordinary curriculum question:")
        result = agent.handle(Task(input="Help me write a learning objective for this unit."))
        print(f"   status={result.status} output={result.output}\n")

        print("2. Reading level estimate (direct tool call):")
        print(f"   'The cat sat.' -> {agent.tools.call('estimate_reading_level', 'The cat sat. It was red.')}\n")

        print("3. Learning-objective format check (direct tool call):")
        print(f"   'Students will analyze the causes' -> {agent.tools.call('check_learning_objective_format', 'Students will analyze the causes')}\n")

        print("4. Guardrail blocking an official-grade request:")
        blocked = agent.handle(Task(input="Please issue the official grade for this student"))
        print(f"   status={blocked.status} reason={blocked.blocked_reason}\n")

        print("5. Sub-agent routing:")
        role = agent.route_to_sub_agent_role(Task(input="Can the tutor explain this again?"))
        print(f"   routed to: {role}")


if __name__ == "__main__":
    main()
