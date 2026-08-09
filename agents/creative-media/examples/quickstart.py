"""Creative & Media Chief Domain Agent -- quickstart.

Runs on MockProvider (no API key, no network). Run directly:

    python agents/creative-media/examples/quickstart.py
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
    "factories/security-factory/python", "agents/creative-media/python",
):
    sys.path.insert(0, str(_ROOT / rel))

from avishkar_agent import Task  # noqa: E402
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router  # noqa: E402

from creative_media_agent import build_creative_media_agent  # noqa: E402


def main() -> None:
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat", "tools"),
                           input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text="Here's a draft to use as a starting point -- adapt it into your own voice.",
    )
    router = Router([provider], RoutingPolicy(default_model="mock-fast"))
    agent = build_creative_media_agent(router, model_override="mock-fast")

    print("1. Ordinary creative-writing question:")
    result = agent.handle(Task(input="Help me draft an opening scene for my short story."))
    print(f"   status={result.status} output={result.output}\n")

    print("2. Word count (direct tool call):")
    print(f"   'The quick brown fox jumps.' -> {agent.tools.call('count_words', 'The quick brown fox jumps.')}\n")

    print("3. Pacing analysis (direct tool call):")
    print(f"   'I ran. I jumped. I fell.' -> {agent.tools.call('analyze_pacing', 'I ran. I jumped. I fell.')}\n")

    print("4. Guardrail blocking a verbatim-reproduction request:")
    blocked = agent.handle(Task(input="Please reproduce the full text of this novel"))
    print(f"   status={blocked.status} reason={blocked.blocked_reason}\n")

    print("5. Sub-agent routing:")
    role = agent.route_to_sub_agent_role(Task(input="Can the story-editor review this?"))
    print(f"   routed to: {role}")


if __name__ == "__main__":
    main()
