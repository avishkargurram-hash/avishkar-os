"""DelegationEngine + ExecutionTracker integration (Priority 17.2,
ADR-0022). See CONTRACT.md SS16.

`execution_tracker=` is optional, so `test_delegation.py`'s existing
suite (which never passes it) proves the zero-regression case. These
tests prove the actual idempotency guarantees: a completed delegation
is never re-invoked, an in-flight or uncertain non-READ operation
refuses a concurrent/recovered retry, and an explicit resolve_unknown()
is the only way past an UNKNOWN outcome.
"""

import tempfile
import unittest
from pathlib import Path

from avishkar_agent import (
    AgentBlueprint,
    ChiefDomainAgent,
    InMemoryMemoryPolicy,
    Orchestrator,
    ToolRegistry,
)
from avishkar_agent.thinking import DEFAULT_THINKING_MODELS
from avishkar_memory import FileMemoryPolicy
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router

from avishkar_layla import LaylaMemoryPolicy, PlanStep
from avishkar_layla.delegation import DelegationEngine
from avishkar_layla.execution import EXEC_FAILED, EXEC_UNKNOWN, ExecutionTracker


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
    """Wraps a real Orchestrator, counting .route() calls -- the proof
    instrument for "the orchestrator was/wasn't invoked again"."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator
        self.call_count = 0

    def route(self, task):
        self.call_count += 1
        return self._orchestrator.route(task)


class TestCompletedDelegationShortCircuits(unittest.TestCase):
    def test_second_call_with_same_key_does_not_reinvoke_orchestrator(self):
        tracker = ExecutionTracker(LaylaMemoryPolicy(InMemoryMemoryPolicy()), clock=lambda: 0.0)
        orchestrator = _CountingOrchestrator(Orchestrator([_agent("finance-agent", "Finance", "the answer")]))
        engine = DelegationEngine(orchestrator, execution_tracker=tracker, clock=lambda: 0.0, sleep_fn=lambda s: None)
        step = PlanStep(id="s1", required_capability="finance-agent", input="search quarterly revenue")

        first = engine.delegate(step, task_id="t1")
        second = engine.delegate(step, task_id="t1")

        self.assertEqual(first.status, "completed")
        self.assertEqual(second.status, "completed")
        self.assertEqual(second.output, first.output)
        self.assertEqual(orchestrator.call_count, 1)  # not called a second time


class TestUncertainTimeoutOnWriteOperation(unittest.TestCase):
    def test_timeout_on_write_marks_unknown_and_blocks_further_retry(self):
        tracker = ExecutionTracker(LaylaMemoryPolicy(InMemoryMemoryPolicy()), clock=lambda: 0.0)
        orchestrator = _CountingOrchestrator(Orchestrator([_agent("finance-agent", "Finance", "x")]))
        # Clock jumps by more than the step's timeout on every call.
        ticks = iter([0.0, 100.0, 100.0, 200.0])
        engine = DelegationEngine(
            orchestrator, execution_tracker=tracker, clock=lambda: next(ticks), sleep_fn=lambda s: None,
        )
        step = PlanStep(
            id="s1", required_capability="finance-agent", input="send an email report to the board",
            timeout_seconds=5.0,
        )

        first = engine.delegate(step, task_id="t1")
        record = tracker.get("t1:s1")

        self.assertEqual(first.status, "timeout")
        self.assertEqual(record.status, EXEC_UNKNOWN)  # not FAILED -- outcome is genuinely uncertain
        self.assertEqual(orchestrator.call_count, 1)

        second = engine.delegate(step, task_id="t1")

        self.assertEqual(second.status, "failed")
        self.assertIn("UNKNOWN", second.error)
        self.assertEqual(orchestrator.call_count, 1)  # refused before touching the orchestrator again

    def test_resolve_unknown_unblocks_a_fresh_retry_through_the_engine(self):
        tracker = ExecutionTracker(LaylaMemoryPolicy(InMemoryMemoryPolicy()), clock=lambda: 0.0)
        orchestrator = _CountingOrchestrator(Orchestrator([_agent("finance-agent", "Finance", "sent")]))
        # First delegate() call: elapsed 100.0 - 0.0 = 100s > 5s timeout.
        # Second (post-resolve_unknown) call: elapsed 201.0 - 200.0 = 1s, completes.
        ticks = iter([0.0, 100.0, 200.0, 201.0])
        engine = DelegationEngine(
            orchestrator, execution_tracker=tracker, clock=lambda: next(ticks), sleep_fn=lambda s: None,
        )
        step = PlanStep(
            id="s1", required_capability="finance-agent", input="send an email report to the board",
            timeout_seconds=5.0,
        )
        engine.delegate(step, task_id="t1")  # times out, lands on UNKNOWN
        self.assertEqual(tracker.get("t1:s1").status, EXEC_UNKNOWN)

        # The uncertain outcome is resolved out-of-band -- e.g. an
        # operator confirmed via the provider's own dashboard that
        # nothing was actually sent -- so a retry is now known-safe.
        tracker.resolve_unknown("t1:s1", EXEC_FAILED, note="confirmed never sent")

        retried = engine.delegate(step, task_id="t1")

        self.assertEqual(retried.status, "completed")
        self.assertEqual(orchestrator.call_count, 2)


class TestReadOperationsAreNotIdempotencyGuarded(unittest.TestCase):
    def test_read_operation_may_retry_even_while_a_prior_attempt_is_unresolved(self):
        tracker = ExecutionTracker(LaylaMemoryPolicy(InMemoryMemoryPolicy()), clock=lambda: 0.0)
        # Simulate a stuck-in-EXECUTING record from some other in-flight
        # attempt for a READ -- retrying a read never duplicates a
        # real-world side effect, so it must not be blocked.
        tracker.begin("t1:s1", "READ", "search quarterly revenue")
        from avishkar_layla.execution import EXEC_EXECUTING
        tracker.transition("t1:s1", EXEC_EXECUTING)

        orchestrator = _CountingOrchestrator(Orchestrator([_agent("finance-agent", "Finance", "the answer")]))
        engine = DelegationEngine(orchestrator, execution_tracker=tracker, clock=lambda: 0.0, sleep_fn=lambda s: None)
        step = PlanStep(id="s1", required_capability="finance-agent", input="search quarterly revenue")

        record = engine.delegate(step, task_id="t1")

        self.assertEqual(record.status, "completed")
        self.assertEqual(orchestrator.call_count, 1)


class TestCrashDuringExecutionRecovery(unittest.TestCase):
    """The load-bearing proof: a fresh ExecutionTracker/DelegationEngine
    pair, in a brand-new process, against the same on-disk backing
    store as a delegation that never reached a terminal state, refuses
    to blindly re-run a non-READ operation -- the same cross-instance
    persistence proof pattern established in test_session.py.
    """

    def test_fresh_instance_refuses_a_write_step_left_executing_by_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            first_process_tracker = ExecutionTracker(LaylaMemoryPolicy(FileMemoryPolicy(Path(tmp))), clock=lambda: 0.0)
            first_process_tracker.begin("t1:s1", "WRITE", "send an email report to the board")
            from avishkar_layla.execution import EXEC_AUTHORIZED, EXEC_APPROVED, EXEC_EXECUTING
            first_process_tracker.transition("t1:s1", EXEC_AUTHORIZED)
            first_process_tracker.transition("t1:s1", EXEC_APPROVED)
            first_process_tracker.transition("t1:s1", EXEC_EXECUTING)
            # ... process dies here, before ever recording a terminal outcome.

            second_process_tracker = ExecutionTracker(LaylaMemoryPolicy(FileMemoryPolicy(Path(tmp))), clock=lambda: 0.0)
            orchestrator = _CountingOrchestrator(Orchestrator([_agent("finance-agent", "Finance", "sent")]))
            engine = DelegationEngine(
                orchestrator, execution_tracker=second_process_tracker, clock=lambda: 0.0, sleep_fn=lambda s: None,
            )
            step = PlanStep(id="s1", required_capability="finance-agent", input="send an email report to the board")

            record = engine.delegate(step, task_id="t1")

            self.assertEqual(record.status, "failed")
            self.assertIn("EXECUTING", record.error)
            self.assertEqual(orchestrator.call_count, 0)  # never re-attempted the possible duplicate send


if __name__ == "__main__":
    unittest.main()
