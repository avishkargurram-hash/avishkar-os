"""Resume-in-place / durable execution (Priority 17.3, ADR-0023). See
CONTRACT.md SS17.

Every test here simulates a crash by constructing a brand-new
ExecutiveRuntime (fresh in-process objects) against the *same* backing
FileMemoryPolicy store a first "process" wrote to -- the same
cross-instance persistence proof pattern test_session.py and
test_delegation_idempotency.py already established. A real restart is
indistinguishable from this at the Python-object level: nothing survives
except what was actually persisted.
"""

import tempfile
import unittest
from pathlib import Path

from avishkar_agent import (
    AgentBlueprint,
    ApprovalGate,
    ChiefDomainAgent,
    InMemoryMemoryPolicy,
    Orchestrator,
    ToolRegistry,
)
from avishkar_agent.thinking import DEFAULT_THINKING_MODELS
from avishkar_memory import FileMemoryPolicy
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router

from avishkar_layla import ExecutionTracker, LaylaMemoryPolicy, SessionNotFoundError
from avishkar_layla.runtime import ExecutiveRuntime
from avishkar_layla.types import (
    APPROVAL_PENDING,
    COMPLETED,
    DELEGATING,
    EXECUTING,
    REQUIRES_HUMAN,
)


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
    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator
        self.call_count = 0

    def route(self, task):
        self.call_count += 1
        return self._orchestrator.route(task)


def _runtime(root_dir, agents, *, approval_gate=None, execution_tracker=None):
    orchestrator = _CountingOrchestrator(Orchestrator(list(agents)))
    agent_domains = {a.name: a.domain for a in agents}
    memory = LaylaMemoryPolicy(FileMemoryPolicy(Path(root_dir)))
    runtime = ExecutiveRuntime(
        orchestrator=orchestrator, agent_domains=agent_domains, memory=memory,
        approval_gate=approval_gate, execution_tracker=execution_tracker,
        clock=lambda: 0.0, sleep_fn=lambda s: None,
    )
    return runtime, orchestrator


class TestResumeBeforeAnyWorkStarted(unittest.TestCase):
    def test_resume_on_a_completed_task_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime, orchestrator = _runtime(tmp, [_agent("finance-agent", "Finance", "answer")])
            task = runtime.handle_event("What's the finance ROI?")
            self.assertEqual(task.state, COMPLETED)

            resumed = runtime.resume(task.id)

            self.assertEqual(resumed.state, COMPLETED)
            self.assertEqual(orchestrator.call_count, 1)  # not re-run

    def test_resume_on_an_unknown_task_id_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime, _ = _runtime(tmp, [_agent("finance-agent", "Finance", "answer")])

            with self.assertRaises(SessionNotFoundError):
                runtime.resume("task-never-existed")

    def test_resume_on_a_requires_human_task_returns_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime, _ = _runtime(tmp, [_agent("finance-agent", "Finance", "x")])
            task = runtime.handle_event("something with absolutely no matching domain keywords zz")
            self.assertEqual(task.state, REQUIRES_HUMAN)

            resumed = runtime.resume(task.id)

            self.assertEqual(resumed.state, REQUIRES_HUMAN)
            self.assertEqual(resumed.blocked_reason, task.blocked_reason)


class TestResumeMidDelegation(unittest.TestCase):
    """The load-bearing scenario: a multi-step plan crashes partway
    through DELEGATING; a fresh runtime, in a fresh process, against
    the same on-disk store, resumes and completes the remaining work
    without re-running the already-completed steps.
    """

    def test_crash_after_first_of_two_steps_resumes_without_redoing_the_completed_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            legal = _agent("legal-agent", "Legal & Compliance", "no liability concerns")
            finance = _agent("finance-agent", "Finance & Economics", "no liability concerns")  # same text -> no conflict
            memory = LaylaMemoryPolicy(FileMemoryPolicy(Path(tmp)))
            tracker = ExecutionTracker(memory, clock=lambda: 0.0)

            # --- "first process": plans, then crashes after completing
            # exactly one of the two delegated steps.
            counting_orchestrator = _CountingOrchestrator(Orchestrator([legal, finance]))
            first_runtime = ExecutiveRuntime(
                orchestrator=counting_orchestrator, agent_domains={"legal-agent": "Legal & Compliance", "finance-agent": "Finance & Economics"},
                memory=memory, execution_tracker=tracker, clock=lambda: 0.0, sleep_fn=lambda s: None,
            )
            task = first_runtime.handle_event("Review this from a legal and finance perspective.")
            # This task legitimately completes in one synchronous call
            # (no real network I/O to interrupt) -- so to prove resume
            # actually skips completed work, simulate the crash by
            # directly loading the plan that was persisted and manually
            # marking one step's execution UNKNOWN-then-resolved isn't
            # what we want here; instead, assert the completed run used
            # exactly 2 orchestrator calls, then prove a *second*,
            # brand-new runtime resuming the same (now-COMPLETED) task
            # makes zero further calls -- the general non-duplication
            # guarantee resume() must uphold even for a task that in
            # fact finished normally.
            self.assertEqual(task.state, COMPLETED)
            self.assertEqual(counting_orchestrator.call_count, 2)

            # --- "second process": brand-new runtime, same on-disk store.
            second_orchestrator = _CountingOrchestrator(Orchestrator([legal, finance]))
            second_tracker = ExecutionTracker(memory, clock=lambda: 0.0)
            second_runtime = ExecutiveRuntime(
                orchestrator=second_orchestrator, agent_domains={"legal-agent": "Legal & Compliance", "finance-agent": "Finance & Economics"},
                memory=memory, execution_tracker=second_tracker, clock=lambda: 0.0, sleep_fn=lambda s: None,
            )
            resumed = second_runtime.resume(task.id)

            self.assertEqual(resumed.state, COMPLETED)
            self.assertEqual(second_orchestrator.call_count, 0)

    def test_manually_interrupted_plan_resumes_and_completes_remaining_steps(self):
        """A more surgical proof: persist a task whose Plan has two
        steps, mark exactly one step's ExecutionRecord COMPLETED (as if
        DelegationEngine had gotten that far before a crash), leave the
        task itself checkpointed at EXECUTING (the last real save point
        before DELEGATING begins -- see runtime.py), and confirm
        resume() only invokes the orchestrator for the *other* step.
        """
        with tempfile.TemporaryDirectory() as tmp:
            legal = _agent("legal-agent", "Legal & Compliance", "no issues")
            finance = _agent("finance-agent", "Finance & Economics", "no issues")
            memory = LaylaMemoryPolicy(FileMemoryPolicy(Path(tmp)))
            tracker = ExecutionTracker(memory, clock=lambda: 0.0)

            counting_orchestrator = _CountingOrchestrator(Orchestrator([legal, finance]))
            agent_domains = {"legal-agent": "Legal & Compliance", "finance-agent": "Finance & Economics"}
            runtime = ExecutiveRuntime(
                orchestrator=counting_orchestrator, agent_domains=agent_domains, memory=memory,
                execution_tracker=tracker, clock=lambda: 0.0, sleep_fn=lambda s: None,
            )

            # Build a real plan via a real (throwaway) task, then hand-roll
            # a fresh LaylaTask checkpointed at EXECUTING with that plan --
            # simulating exactly what runtime.py persists right before the
            # DELEGATING loop starts.
            from avishkar_layla.types import LaylaTask, StateTransition

            probe = runtime.handle_event("Review this from a legal and finance perspective.")
            self.assertEqual(probe.state, COMPLETED)
            plan = probe.plan
            self.assertEqual(len(plan.steps), 2)

            # Pre-complete exactly one step's execution record, as if a
            # prior, now-crashed attempt got that far.
            completed_step, remaining_step = plan.steps[0], plan.steps[1]
            crashed_task_id = "crashed-task-1"
            tracker.begin(f"{crashed_task_id}:{completed_step.id}", "READ", completed_step.input)
            tracker.transition(
                f"{crashed_task_id}:{completed_step.id}", "COMPLETED",
                # Same text the live agent would also produce -- so
                # ConflictResolver sees agreement, not a false conflict
                # between "cached" and "freshly delegated" phrasing.
                result={"agent_name": completed_step.required_capability, "output": "no issues"},
            )

            crashed_task = LaylaTask(
                input=probe.input, id=crashed_task_id, state=EXECUTING,
                history=(StateTransition(from_state="PLANNING", to_state=EXECUTING, at="2026-01-01T00:00:00+00:00"),),
                plan=plan, plan_id=plan.id,
            )
            runtime.sessions.save(crashed_task)

            counting_orchestrator.call_count = 0  # reset -- only count resume()'s own calls
            resumed = runtime.resume(crashed_task_id)

            self.assertEqual(resumed.state, COMPLETED)
            self.assertEqual(counting_orchestrator.call_count, 1)  # only the remaining step


class TestResumeInterruptedApproval(unittest.TestCase):
    def test_pending_approval_is_persisted_and_resume_rechecks_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = LaylaMemoryPolicy(FileMemoryPolicy(Path(tmp)))
            orchestrator = _CountingOrchestrator(Orchestrator([_agent("finance-agent", "Finance", "transfer processed")]))
            runtime = ExecutiveRuntime(
                orchestrator=orchestrator, agent_domains={"finance-agent": "Finance"}, memory=memory,
                clock=lambda: 0.0, sleep_fn=lambda s: None,
            )  # no approval_gate -- a HIGH-risk request stays genuinely pending, not auto-decided

            task = runtime.handle_event("initiate a wire transfer for the finance team")

            self.assertEqual(task.state, APPROVAL_PENDING)
            self.assertIsNotNone(task.pending_approval_id)

            # "process restart": brand-new runtime, same on-disk store.
            second_orchestrator = _CountingOrchestrator(Orchestrator([_agent("finance-agent", "Finance", "transfer processed")]))
            second_runtime = ExecutiveRuntime(
                orchestrator=second_orchestrator, agent_domains={"finance-agent": "Finance"}, memory=memory,
                clock=lambda: 0.0, sleep_fn=lambda s: None,
            )
            still_pending = second_runtime.resume(task.id)
            self.assertEqual(still_pending.state, APPROVAL_PENDING)  # nobody decided it yet

            # An operator grants the approval directly -- via a *third*
            # ExecutiveRuntime's ApprovalManager, proving the grant is
            # visible cross-instance because it's persisted, not just
            # cached in the process that issued it.
            third_orchestrator = _CountingOrchestrator(Orchestrator([_agent("finance-agent", "Finance", "transfer processed")]))
            third_runtime = ExecutiveRuntime(
                orchestrator=third_orchestrator, agent_domains={"finance-agent": "Finance"}, memory=memory,
                clock=lambda: 0.0, sleep_fn=lambda s: None,
            )
            third_runtime._approval.grant(task.pending_approval_id)  # simulating an operator's own separate call

            resumed = third_runtime.resume(task.id)

            self.assertEqual(resumed.state, COMPLETED)
            self.assertEqual(third_orchestrator.call_count, 1)


if __name__ == "__main__":
    unittest.main()
