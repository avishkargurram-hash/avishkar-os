"""PlanStep.depends_on enforcement (Mission Layla, Phase 5.1). See
CONTRACT.md SS5-6 and the Phase 5 plan section.

PlanStep.depends_on existed in the dataclass from the start but was never
enforced -- every step in a Plan ran in list order regardless of whether an
earlier dependency had failed. These tests construct a Plan directly
(bypassing Planner, which never sets depends_on today -- see planning.py)
with a deliberately-failing first step and a second step that depends on
it, confirming the second step is skipped -- marked "failed" with a real
dependency error -- rather than executed anyway. Same surgical
hand-rolled-Plan-at-EXECUTING pattern test_resume.py already established.
"""

import unittest

from avishkar_agent import (
    AgentBlueprint,
    ChiefDomainAgent,
    InMemoryMemoryPolicy,
    Orchestrator,
    ToolRegistry,
)
from avishkar_agent.thinking import DEFAULT_THINKING_MODELS
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router

from avishkar_layla import LaylaMemoryPolicy
from avishkar_layla.runtime import ExecutiveRuntime
from avishkar_layla.types import EXECUTING, REQUIRES_HUMAN, LaylaTask, Plan, PlanStep, StateTransition, new_id


def _agent(name: str, domain: str, response_text: str) -> ChiefDomainAgent:
    blueprint = AgentBlueprint(name=name, domain=domain, version="0.1.0", mission="test", default_model="mock-fast")
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat",),
                           input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text=response_text,
    )
    router = Router([provider], RoutingPolicy(default_model="mock-fast"))
    return ChiefDomainAgent(blueprint, router, InMemoryMemoryPolicy(), ToolRegistry(), DEFAULT_THINKING_MODELS)


class _CountingOrchestrator:
    """Same real-call-counting wrapper test_resume.py uses -- proves the
    orchestrator was never actually invoked for a skipped step, not just
    that its DelegationRecord happens to say "failed" for some other reason."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator
        self.routed_task_types = []

    def route(self, task):
        self.routed_task_types.append(task.task_type)
        return self._orchestrator.route(task)


class TestPlanStepDependsOnEnforcement(unittest.TestCase):
    def _runtime(self, agents):
        orchestrator = _CountingOrchestrator(Orchestrator(list(agents)))
        agent_domains = {a.name: a.domain for a in agents}
        memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        runtime = ExecutiveRuntime(
            orchestrator=orchestrator, agent_domains=agent_domains, memory=memory,
            clock=lambda: 0.0, sleep_fn=lambda s: None,
        )
        return runtime, orchestrator

    def test_dependent_step_is_skipped_when_its_dependency_fails(self):
        working_agent = _agent("finance-agent", "Finance", "no issues")
        runtime, orchestrator = self._runtime([working_agent])

        failing_step = PlanStep(id=new_id("step"), required_capability="capability-with-no-registered-agent",
                                 input="do the impossible thing")
        dependent_step = PlanStep(id=new_id("step"), required_capability="finance-agent",
                                   input="only run after the impossible thing", depends_on=(failing_step.id,))
        plan = Plan(id=new_id("plan"), task_id="task-under-test", steps=(failing_step, dependent_step))

        task = LaylaTask(
            input="a task whose plan has a real dependency chain", id="task-under-test", state=EXECUTING,
            history=(StateTransition(from_state="PLANNING", to_state=EXECUTING, at="2026-01-01T00:00:00+00:00"),),
            plan=plan, plan_id=plan.id,
        )
        runtime.sessions.save(task)

        resumed = runtime.resume(task.id)

        # The orchestrator was invoked for the failing step's capability
        # (real attempt, real NoMatchingAgentError) but NEVER for the
        # dependent step's -- proof this is a genuine skip, not merely a
        # record relabeled "failed" after actually running it.
        self.assertEqual(orchestrator.routed_task_types, ["capability-with-no-registered-agent"])

        # Zero real successes -> Phase 0.2's total-failure check applies;
        # the task is honestly REQUIRES_HUMAN, never a false COMPLETED.
        self.assertEqual(resumed.state, REQUIRES_HUMAN)
        self.assertIn("dependency not satisfied", resumed.blocked_reason)
        self.assertIn(dependent_step.id, resumed.blocked_reason)

    def test_step_with_no_dependencies_is_unaffected(self):
        """Backward compatibility, explicit: a Plan where every step has
        depends_on=() (exactly what Planner.plan() produces today) behaves
        identically to before this phase -- zero behavior change for any
        caller that never sets depends_on."""
        working_agent = _agent("finance-agent", "Finance", "no issues")
        runtime, orchestrator = self._runtime([working_agent])

        step = PlanStep(id=new_id("step"), required_capability="finance-agent", input="what's the ROI")
        plan = Plan(id=new_id("plan"), task_id="task-no-deps", steps=(step,))
        task = LaylaTask(
            input="what's the ROI", id="task-no-deps", state=EXECUTING,
            history=(StateTransition(from_state="PLANNING", to_state=EXECUTING, at="2026-01-01T00:00:00+00:00"),),
            plan=plan, plan_id=plan.id,
        )
        runtime.sessions.save(task)

        resumed = runtime.resume(task.id)

        self.assertEqual(orchestrator.routed_task_types, ["finance-agent"])
        self.assertEqual(resumed.state, "COMPLETED")

    def test_dependent_step_runs_normally_once_its_dependency_completes(self):
        """The positive case: a step whose real dependency DID complete
        still executes normally -- this phase only skips genuinely
        unsatisfied dependencies, never a satisfied one."""
        legal = _agent("legal-agent", "Legal", "no issues")
        finance = _agent("finance-agent", "Finance", "no issues")
        runtime, orchestrator = self._runtime([legal, finance])

        first_step = PlanStep(id=new_id("step"), required_capability="legal-agent", input="check legal")
        second_step = PlanStep(id=new_id("step"), required_capability="finance-agent",
                                input="check finance after legal", depends_on=(first_step.id,))
        plan = Plan(id=new_id("plan"), task_id="task-satisfied-dep", steps=(first_step, second_step))
        task = LaylaTask(
            input="check legal then finance", id="task-satisfied-dep", state=EXECUTING,
            history=(StateTransition(from_state="PLANNING", to_state=EXECUTING, at="2026-01-01T00:00:00+00:00"),),
            plan=plan, plan_id=plan.id,
        )
        runtime.sessions.save(task)

        resumed = runtime.resume(task.id)

        self.assertEqual(orchestrator.routed_task_types, ["legal-agent", "finance-agent"])
        self.assertEqual(resumed.state, "COMPLETED")


if __name__ == "__main__":
    unittest.main()
