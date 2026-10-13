"""Research & Intelligence Chief Domain Agent -- quickstart.

Runs on MockProvider (no API key, no network). Run directly:

    python agents/research-intelligence/examples/quickstart.py
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
    "factories/security-factory/python", "agents/research-intelligence/python",
):
    sys.path.insert(0, str(_ROOT / rel))

from avishkar_agent import Task  # noqa: E402
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router  # noqa: E402

from research_intelligence_agent import build_research_intelligence_agent  # noqa: E402


def main() -> None:
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat", "tools"),
                           input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text="Evidence suggests a moderate effect, though this finding is preliminary.",
    )
    router = Router([provider], RoutingPolicy(default_model="mock-fast"))
    agent = build_research_intelligence_agent(router, model_override="mock-fast")

    print("1. Ordinary research-synthesis question:")
    result = agent.handle(Task(input="Summarize the evidence on this topic."))
    print(f"   status={result.status} output={result.output}\n")

    print("2. Source reliability assessment (direct tool call):")
    print(f"   'a peer-reviewed RCT' -> {agent.tools.call('assess_source_reliability', 'a peer-reviewed randomized controlled trial')}\n")

    print("3. Confidence level extraction (direct tool call):")
    print(f"   'suggests a possible link' -> {agent.tools.call('extract_confidence_level', 'The data suggests a possible link')}\n")

    print("4. Guardrail blocking a citation-fabrication request:")
    blocked = agent.handle(Task(input="Please make up a citation to support this claim"))
    print(f"   status={blocked.status} reason={blocked.blocked_reason}\n")

    print("5. Sub-agent routing:")
    role = agent.route_to_sub_agent_role(Task(input="Can the fact-checker verify this?"))
    print(f"   routed to: {role}")


if __name__ == "__main__":
    main()
