"""Human Development & Psychology Chief Domain Agent -- quickstart.

Runs on MockProvider (no API key, no network). Run directly:

    python agents/human-development-psychology/examples/quickstart.py
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
    "factories/security-factory/python", "agents/human-development-psychology/python",
):
    sys.path.insert(0, str(_ROOT / rel))

from avishkar_agent import Task  # noqa: E402
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router  # noqa: E402

from human_development_psychology_agent import build_human_development_psychology_agent  # noqa: E402


def main() -> None:
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat", "tools"),
                           input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text="A therapist or counselor can help you go deeper on this than I can.",
    )
    router = Router([provider], RoutingPolicy(default_model="mock-fast"))

    with tempfile.TemporaryDirectory() as tmp:
        agent = build_human_development_psychology_agent(router, model_override="mock-fast", memory_root_dir=Path(tmp))

        print("1. Ordinary growth question:")
        result = agent.handle(Task(input="How can I communicate better with my partner?"))
        print(f"   status={result.status} output={result.output}\n")

        print("2. Reflection prompt (direct tool call):")
        print(f"   topic='stress' -> {agent.tools.call('suggest_reflection_prompt', 'stress')}\n")

        print("3. THE MOST IMPORTANT CHECK -- crisis language is escalated with real resources, not just blocked:")
        blocked = agent.handle(Task(input="I want to end my life"))
        print(f"   status={blocked.status}")
        print(f"   reason={blocked.blocked_reason}\n")

        print("4. Sub-agent routing:")
        role = agent.route_to_sub_agent_role(Task(input="Can the communication-coach help with this?"))
        print(f"   routed to: {role}")


if __name__ == "__main__":
    main()
