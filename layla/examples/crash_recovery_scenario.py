"""Layla -- resume-in-place / durable execution demonstration
(Priority 17.3 of the Phase 17 directive, ADR-0023).

Scenario (the directive's own example, at a runnable scale): a plan
delegates research on five companies. The process crashes after three
of the five have completed. A fresh ExecutiveRuntime -- new Python
objects, standing in for a brand-new process -- resumes the same task
and completes only the two remaining companies, never re-invoking the
orchestrator for the three already done.

How "crash" is simulated: this script cannot literally kill and
restart its own OS process mid-loop, so it does what every
crash-recovery test in this codebase already does (test_session.py,
test_delegation_idempotency.py, test_resume.py) -- construct a
completely fresh set of runtime objects against the same on-disk
FileMemoryPolicy store a first run wrote to, and prove the second run
picks up exactly where persisted state says the first one stopped.
Nothing here is faked: the on-disk store, the Plan, the
ExecutionRecords, and the second run's orchestrator calls are all real.

Run directly:

    python layla/examples/crash_recovery_scenario.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
for rel in (
    "core/python", "router/python", "factories/agent-factory/python",
    "factories/mcp-factory/python", "factories/knowledge-factory/python",
    "factories/memory-factory/python", "factories/security-factory/python",
    "layla/python",
):
    sys.path.insert(0, str(_ROOT / rel))

from avishkar_agent import (  # noqa: E402
    AgentBlueprint,
    ChiefDomainAgent,
    InMemoryMemoryPolicy,
    Orchestrator,
    ToolRegistry,
)
from avishkar_agent.thinking import DEFAULT_THINKING_MODELS  # noqa: E402
from avishkar_memory import FileMemoryPolicy  # noqa: E402
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router  # noqa: E402

from avishkar_layla import ExecutionTracker, LaylaMemoryPolicy  # noqa: E402
from avishkar_layla.runtime import ExecutiveRuntime  # noqa: E402
from avishkar_layla.types import EXECUTING, LaylaTask, Plan, PlanStep  # noqa: E402

COMPANIES = ["Acme Robotics", "Bluepeak AI", "Cinder Analytics", "Driftwood Labs", "Everline Systems"]


class CountingOrchestrator:
    """Wraps a real Orchestrator, counting .route() calls -- the proof
    instrument for "was the already-completed work re-run."
    """

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator
        self.call_count = 0

    def route(self, task):
        self.call_count += 1
        print(f"    -> orchestrator.route() call #{self.call_count}: {task.input!r}")
        return self._orchestrator.route(task)


def _build_orchestrator() -> Orchestrator:
    blueprint = AgentBlueprint(
        name="research-agent", domain="Research", version="0.1.0",
        mission="research companies", default_model="mock-fast",
    )
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat",),
                           input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text="No material developments found in the last quarter.",
    )
    router = Router([provider], RoutingPolicy(default_model="mock-fast"))
    agent = ChiefDomainAgent(blueprint, router, InMemoryMemoryPolicy(), ToolRegistry(), DEFAULT_THINKING_MODELS)
    return Orchestrator([agent])


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        print("=" * 78)
        print("PHASE 1: build a 5-step plan and simulate a crash after step 3")
        print("=" * 78)

        memory = LaylaMemoryPolicy(FileMemoryPolicy(Path(tmp)))
        tracker = ExecutionTracker(memory)

        plan = Plan(
            id="plan-quarterly-research", task_id="task-quarterly-research",
            steps=tuple(
                PlanStep(id=f"step-{i}", required_capability="research-agent", input=f"Research {company} funding and hiring")
                for i, company in enumerate(COMPANIES)
            ),
        )
        task = LaylaTask(input="Research the latest developments for our watchlist", id="task-quarterly-research",
                          state=EXECUTING, plan=plan, plan_id=plan.id)

        first_orchestrator = CountingOrchestrator(_build_orchestrator())
        first_runtime = ExecutiveRuntime(
            orchestrator=first_orchestrator, agent_domains={"research-agent": "Research"}, memory=memory,
            execution_tracker=tracker,
        )
        first_runtime.sessions.save(task)

        # Simulate the first three steps having already completed
        # before the crash -- this is exactly what DelegationEngine
        # itself would have persisted via ExecutionTracker had this
        # script actually run resume() and been killed partway through.
        for step in plan.steps[:3]:
            key = f"{task.id}:{step.id}"
            tracker.begin(key, "READ", step.input)
            tracker.transition(key, "COMPLETED", result={
                "agent_name": "research-agent",
                "output": "No material developments found in the last quarter.",
            })
            print(f"  [pre-crash] completed: {step.input!r}")

        print(f"  [crash] process dies here -- {5 - 3} of 5 steps never ran")
        print()

        print("=" * 78)
        print("PHASE 2: a fresh process resumes the same task")
        print("=" * 78)

        second_orchestrator = CountingOrchestrator(_build_orchestrator())
        second_tracker = ExecutionTracker(memory)  # brand-new instance, same on-disk store
        second_runtime = ExecutiveRuntime(
            orchestrator=second_orchestrator, agent_domains={"research-agent": "Research"}, memory=memory,
            execution_tracker=second_tracker,
        )

        resumed = second_runtime.resume(task.id)

        print()
        print("=" * 78)
        print("RESULT")
        print("=" * 78)
        print(f"  final task state:              {resumed.state}")
        print(f"  orchestrator calls this run:    {second_orchestrator.call_count} (expected 2 -- only the 2 unfinished companies)")
        print(f"  total steps in plan:            {len(plan.steps)}")
        assert resumed.state == "COMPLETED", "expected the resumed task to complete"
        assert second_orchestrator.call_count == 2, "expected exactly the 2 not-yet-completed steps to run"
        print()
        print("  Confirmed: the 3 pre-crash-completed steps were never re-delegated.")
        print(f"  Executive summary:\n{resumed.result}")


if __name__ == "__main__":
    main()
