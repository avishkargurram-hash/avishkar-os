"""Prompt Framework -- quickstart.

Registers two versions of a support-agent prompt, evaluates both against
the same eval cases, compares them, and feeds the winning version's
rendered text into a real ChiefDomainAgent's Task -- no agent-factory
bridge needed since a rendered prompt is just a str (Task.input's type
since Phase 3). Run directly:

    python factories/prompt-factory/examples/quickstart.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT / "core" / "python"))
sys.path.insert(0, str(_ROOT / "router" / "python"))
sys.path.insert(0, str(_ROOT / "factories" / "agent-factory" / "python"))
sys.path.insert(0, str(_ROOT / "factories" / "prompt-factory" / "python"))

from avishkar_agent import AgentBlueprint, ChiefDomainAgent, InMemoryMemoryPolicy, Task, ToolRegistry  # noqa: E402
from avishkar_agent.thinking import DEFAULT_THINKING_MODELS  # noqa: E402
from avishkar_router import ModelSpec, MockProvider, Router, RoutingPolicy  # noqa: E402

from avishkar_prompt import (  # noqa: E402
    EvalCase,
    PromptRegistry,
    PromptVariable,
    PromptVersion,
    compare_versions,
    evaluate_version,
    keyword_presence_scorer,
)


def main() -> None:
    registry = PromptRegistry()
    registry.register(
        "support-question",
        PromptVersion(
            version="1.0.0",
            template="{question}",
            variables=(PromptVariable(name="question"),),
        ),
    )
    registry.register(
        "support-question",
        PromptVersion(
            version="2.0.0",
            template=(
                "You are a support agent. Answer using only company policy. "
                "Cite the policy if relevant.\nQuestion: {question}"
            ),
            variables=(PromptVariable(name="question"),),
        ),
    )

    cases = [
        EvalCase(
            inputs={"question": "what do I need before deploying to production"},
            expected=["policy", "answer using only"],
        )
    ]

    print("1. Evaluating both prompt versions against the same eval case:")
    report_v1 = evaluate_version(registry, "support-question", "1.0.0", cases, keyword_presence_scorer)
    report_v2 = evaluate_version(registry, "support-question", "2.0.0", cases, keyword_presence_scorer)
    comparison = compare_versions(report_v1, report_v2)
    print(f"   v1.0.0 average={report_v1.average:.2f}  v2.0.0 average={report_v2.average:.2f}")
    print(f"   v2.0.0 improved over v1.0.0: {comparison.improved} (delta={comparison.delta:+.2f})\n")

    print("2. Rendering the winning version and feeding it to a real ChiefDomainAgent:")
    winning_version = "2.0.0" if comparison.improved else "1.0.0"
    rendered = registry.render(
        "support-question", {"question": "What do I need before deploying to production?"}, version=winning_version
    )

    blueprint = AgentBlueprint(
        name="support-agent", domain="Support", version="0.1.0",
        mission="Answer employee questions using company policy.",
        default_model="mock-fast",
    )
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat",),
                           input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text="Per policy: a passing test suite and a second reviewer.",
    )
    router = Router([provider], RoutingPolicy(default_model="mock-fast"))
    agent = ChiefDomainAgent(blueprint, router, InMemoryMemoryPolicy(), ToolRegistry(), DEFAULT_THINKING_MODELS)

    result = agent.handle(Task(input=rendered))
    print(f"   rendered prompt (v{winning_version}): {rendered[:70]}...")
    print(f"   agent status={result.status} output={result.output}")


if __name__ == "__main__":
    main()
