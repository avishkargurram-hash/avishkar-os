"""Evaluation Framework -- quickstart.

Builds a real ChiefDomainAgent whose QualityGate is produced by
make_quality_gate() (not hand-written), so the agent's own reasoning
loop is genuinely gated by this framework -- then separately evaluates
a WorkflowResult, and compares two prompt versions via the reused
compare_versions(). Run directly:

    python factories/evaluation-factory/examples/quickstart.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
for rel in (
    "core/python", "router/python",
    "factories/agent-factory/python", "factories/mcp-factory/python",
    "factories/knowledge-factory/python", "factories/workflow-factory/python",
    "factories/prompt-factory/python", "factories/evaluation-factory/python",
):
    sys.path.insert(0, str(_ROOT / rel))

from avishkar_agent import AgentBlueprint, ChiefDomainAgent, InMemoryMemoryPolicy, Task, ToolRegistry  # noqa: E402
from avishkar_agent.thinking import DEFAULT_THINKING_MODELS  # noqa: E402
from avishkar_router import ModelSpec, MockProvider, Router, RoutingPolicy  # noqa: E402
from avishkar_workflow import WorkflowResult  # noqa: E402

from avishkar_evaluation import (  # noqa: E402
    EvalCase,
    EvalSuite,
    evaluate_workflow_result,
    keyword_presence_scorer,
    make_quality_gate,
)


def main() -> None:
    print("1. A real ChiefDomainAgent gated by a QualityGate this framework built:")
    suite = EvalSuite(
        name="mentions-policy",
        cases=(EvalCase(inputs={}, expected=["policy", "test suite"]),),
    )
    gate = make_quality_gate("mentions-policy", suite, keyword_presence_scorer, threshold=1.0)

    blueprint = AgentBlueprint(
        name="support-agent", domain="Support", version="0.1.0",
        mission="Answer using company policy.", default_model="mock-fast",
    )
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat",),
                           input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text="Per policy, a passing test suite is required.",
    )
    router = Router([provider], RoutingPolicy(default_model="mock-fast"))
    agent = ChiefDomainAgent(
        blueprint, router, InMemoryMemoryPolicy(), ToolRegistry(), DEFAULT_THINKING_MODELS,
        quality_gates=(gate,),
    )
    result = agent.handle(Task(input="What do I need before deploying?"))
    print(f"   agent status={result.status} (quality gate {'passed' if result.status == 'completed' else 'failed'})\n")

    print("2. Evaluating a WorkflowResult's final state:")
    workflow_result = WorkflowResult(state={"output": "Per policy, a passing test suite is required."}, history=(), status="completed")
    report = evaluate_workflow_result(workflow_result, suite, keyword_presence_scorer)
    print(f"   average score={report.average}\n")

    print("3. Comparing prompt versions (compare_versions reused from prompt-factory):")
    from avishkar_evaluation import compare_versions
    from avishkar_prompt import EvalReport
    weak = EvalReport(scores=(0.3,), average=0.3)
    strong = EvalReport(scores=(0.9,), average=0.9)
    comparison = compare_versions(weak, strong)
    print(f"   improved={comparison.improved} delta={comparison.delta:+.2f}")


if __name__ == "__main__":
    main()
