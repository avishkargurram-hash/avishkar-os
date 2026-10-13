"""Concurrency & event system hardening (Priority 17.4, ADR-0024). See
CONTRACT.md SS18 and README.md's concurrency model.

Every test here uses real `threading.Thread`s, not sequential
simulation -- a lock that only "looks right" under single-threaded
execution isn't proof of anything. Where the race window is too narrow
to hit reliably under the GIL's natural scheduling, a small test double
that sleeps mid-operation widens it deterministically, combined with a
`threading.Barrier` so every thread starts its critical section at
exactly the same moment.
"""

import tempfile
import threading
import time
import unittest
from pathlib import Path

from avishkar_agent import (
    AgentBlueprint,
    ChiefDomainAgent,
    InMemoryMemoryPolicy,
    MemoryPolicy,
    Orchestrator,
    ToolRegistry,
)
from avishkar_agent.thinking import DEFAULT_THINKING_MODELS
from avishkar_memory import FileMemoryPolicy
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router

from avishkar_layla import ExecutionTracker, LaylaMemoryPolicy
from avishkar_layla.approval import ApprovalManager
from avishkar_layla.audit import AuditLogger
from avishkar_layla.delegation import DelegationEngine
from avishkar_layla.runtime import ExecutiveRuntime
from avishkar_layla.scheduler import Scheduler
from avishkar_layla.session import SessionManager
from avishkar_layla.state_machine import StateMachine
from avishkar_layla.types import COMPLETED, RISK_HIGH, UNDERSTANDING, LaylaTask, PlanStep


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


class _SlowMemoryPolicy(MemoryPolicy):
    """Wraps a real MemoryPolicy backend, sleeping briefly inside every
    recall() -- deliberately widens the check-then-act race window a
    lock is supposed to close, so a race is reproduced deterministically
    rather than hoped for under natural GIL scheduling.
    """

    def __init__(self, backend: MemoryPolicy, *, delay_seconds: float = 0.02) -> None:
        self._backend = backend
        self._delay = delay_seconds

    def remember(self, kind, key, value):
        self._backend.remember(kind, key, value)

    def recall(self, kind, key):
        time.sleep(self._delay)
        return self._backend.recall(kind, key)

    def forget(self, kind, key):
        self._backend.forget(kind, key)


class TestConcurrentExecutionTrackerBegin(unittest.TestCase):
    def test_two_threads_racing_begin_on_the_same_key_only_one_claims_it(self):
        memory = LaylaMemoryPolicy(_SlowMemoryPolicy(InMemoryMemoryPolicy()))
        tracker = ExecutionTracker(memory)
        barrier = threading.Barrier(2)
        results = [None, None]

        def worker(i):
            barrier.wait()  # both threads call begin() at the same instant
            record = tracker.begin("shared-key", "WRITE", "send an email")
            results[i] = getattr(record, "claimed_this_call", False)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(sorted(results), [False, True])  # exactly one claimed it

    def test_ten_threads_racing_begin_on_the_same_key_exactly_one_claims_it(self):
        memory = LaylaMemoryPolicy(_SlowMemoryPolicy(InMemoryMemoryPolicy(), delay_seconds=0.01))
        tracker = ExecutionTracker(memory)
        barrier = threading.Barrier(10)
        claims = []
        claims_lock = threading.Lock()

        def worker():
            barrier.wait()
            record = tracker.begin("shared-key", "WRITE", "send an email")
            if getattr(record, "claimed_this_call", False):
                with claims_lock:
                    claims.append(1)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(claims), 1)


class TestConcurrentDelegationDoesNotDuplicateSideEffects(unittest.TestCase):
    def test_duplicate_concurrent_delegate_calls_only_invoke_orchestrator_once(self):
        """The end-to-end proof: two threads deliver what amounts to a
        duplicate event for the same plan step at the same time (e.g. an
        at-least-once event bus redelivery). Exactly one actually
        invokes the orchestrator; the other is refused, not silently
        duplicated.
        """
        memory = LaylaMemoryPolicy(_SlowMemoryPolicy(InMemoryMemoryPolicy()))
        tracker = ExecutionTracker(memory)

        call_count = [0]
        call_lock = threading.Lock()
        orchestrator = Orchestrator([_agent("finance-agent", "Finance", "the answer")])

        class _CountingOrchestrator:
            def route(self, task):
                with call_lock:
                    call_count[0] += 1
                return orchestrator.route(task)

        engine = DelegationEngine(_CountingOrchestrator(), execution_tracker=tracker, sleep_fn=lambda s: None)
        # A WRITE-classified input -- READ operations are deliberately
        # exempt from the duplicate-call guard (retrying a read never
        # duplicates a real effect), so this must not use a "search"/
        # "inspect"/etc-worded input or it wouldn't exercise the guard.
        step = PlanStep(id="s1", required_capability="finance-agent", input="send an email report to the board")

        barrier = threading.Barrier(2)
        outcomes = []
        outcomes_lock = threading.Lock()

        def worker():
            barrier.wait()
            record = engine.delegate(step, task_id="t1")
            with outcomes_lock:
                outcomes.append(record.status)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(call_count[0], 1)  # never duplicated
        self.assertIn("completed", outcomes)


class TestConcurrentApprovalDecisions(unittest.TestCase):
    def test_simultaneous_grant_calls_leave_a_single_consistent_outcome(self):
        manager = ApprovalManager()
        request = manager.request("task-1", "wire transfer", RISK_HIGH)
        barrier = threading.Barrier(5)

        def worker():
            barrier.wait()
            try:
                manager.grant(request.id, reason="concurrent grant")
            except Exception:  # noqa: BLE001 -- some callers may lose a benign race, that's fine
                pass

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(manager.check(request.id), "granted")

    def test_grant_and_deny_racing_produce_one_final_status_not_corruption(self):
        manager = ApprovalManager()
        request = manager.request("task-1", "wire transfer", RISK_HIGH)
        barrier = threading.Barrier(2)

        def grant_worker():
            barrier.wait()
            try:
                manager.grant(request.id)
            except Exception:  # noqa: BLE001
                pass

        def deny_worker():
            barrier.wait()
            try:
                manager.deny(request.id)
            except Exception:  # noqa: BLE001
                pass

        t1, t2 = threading.Thread(target=grant_worker), threading.Thread(target=deny_worker)
        t1.start(); t2.start()
        t1.join(); t2.join()

        # Whichever wins, the result is one of exactly the two valid
        # statuses -- never a torn/partial write.
        self.assertIn(manager.check(request.id), ("granted", "denied"))


class TestConcurrentMemoryWrites(unittest.TestCase):
    def test_concurrent_remember_calls_for_different_keys_all_survive(self):
        """FileMemoryPolicy's load-mutate-save cycle is the real risk:
        without a lock, N concurrent remember() calls for the SAME kind
        (different keys) can each load the same on-disk snapshot and
        the last writer silently discards every other writer's key.
        """
        with tempfile.TemporaryDirectory() as tmp:
            backend = FileMemoryPolicy(Path(tmp))
            barrier = threading.Barrier(20)

            def worker(i):
                barrier.wait()
                backend.remember("long_term", f"key-{i}", {"n": i})

            threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            for i in range(20):
                self.assertEqual(backend.recall("long_term", f"key-{i}"), {"n": i})


class TestConcurrentAuditWrites(unittest.TestCase):
    def test_concurrent_record_calls_for_the_same_task_lose_nothing(self):
        memory = LaylaMemoryPolicy(_SlowMemoryPolicy(InMemoryMemoryPolicy(), delay_seconds=0.005))
        logger = AuditLogger(memory)
        barrier = threading.Barrier(15)

        def worker(i):
            barrier.wait()
            logger.record("layla.test.event", {"i": i}, task_id="t1")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(15)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        history = logger.history("t1")
        self.assertEqual(len(history), 15)  # none silently overwritten


class TestConcurrentSessionSaves(unittest.TestCase):
    def test_concurrent_save_calls_for_different_tasks_all_appear_in_the_index(self):
        memory = LaylaMemoryPolicy(_SlowMemoryPolicy(InMemoryMemoryPolicy()))
        manager = SessionManager(memory)
        sm = StateMachine()
        barrier = threading.Barrier(10)
        tasks = []
        for i in range(10):
            task = LaylaTask(input=f"task {i}")
            sm.transition(task, UNDERSTANDING)
            tasks.append(task)

        def worker(task):
            barrier.wait()
            manager.save(task)

        threads = [threading.Thread(target=worker, args=(t,)) for t in tasks]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        incomplete_ids = {t.id for t in manager.list_incomplete()}
        self.assertEqual(incomplete_ids, {t.id for t in tasks})


class TestConcurrentScheduler(unittest.TestCase):
    def test_concurrent_schedule_and_tick_do_not_crash_or_duplicate_fires(self):
        clock = [0.0]
        scheduler = Scheduler(clock=lambda: clock[0])
        fire_counts = {}
        fire_lock = threading.Lock()

        def make_callback(job_key):
            def callback():
                with fire_lock:
                    fire_counts[job_key] = fire_counts.get(job_key, 0) + 1
            return callback

        job_ids = [scheduler.schedule_once(1.0, make_callback(i)) for i in range(20)]

        barrier = threading.Barrier(4)

        def ticker():
            barrier.wait()
            for _ in range(5):
                scheduler.tick(now=1.0)

        def scheduler_adder():
            barrier.wait()
            for i in range(20, 30):
                scheduler.schedule_once(100.0, make_callback(i))  # far in the future, shouldn't fire

        def canceller():
            barrier.wait()
            for job_id in job_ids[:5]:
                scheduler.cancel(job_id)

        threads = [
            threading.Thread(target=ticker), threading.Thread(target=ticker),
            threading.Thread(target=scheduler_adder), threading.Thread(target=canceller),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Every job that fired, fired exactly once -- never duplicated
        # by two ticker threads racing the same due job.
        for count in fire_counts.values():
            self.assertEqual(count, 1)
        # The far-future jobs (scheduled for t=100) never fired at t=1.
        self.assertNotIn(25, fire_counts)


class TestTenSimultaneousTasks(unittest.TestCase):
    def test_ten_concurrent_handle_event_calls_all_complete_independently(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = LaylaMemoryPolicy(FileMemoryPolicy(Path(tmp)))
            orchestrator = Orchestrator([_agent("finance-agent", "Finance", "the ROI looks positive")])
            runtime = ExecutiveRuntime(
                orchestrator=orchestrator, agent_domains={"finance-agent": "Finance"}, memory=memory,
            )
            barrier = threading.Barrier(10)
            results = [None] * 10
            errors = []

            def worker(i):
                barrier.wait()
                try:
                    task = runtime.handle_event(f"What's the projected finance ROI for scenario {i}?")
                    results[i] = task.state
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)

            threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            self.assertEqual(errors, [])
            self.assertEqual(results, [COMPLETED] * 10)

    def test_resume_racing_a_still_in_flight_task_does_not_duplicate_delegation(self):
        """Two threads both call resume() on the same, already-EXECUTING
        task at the same time -- the per-task-id lock (Priority 17.4)
        must serialize them so the second one, once unblocked, re-reads
        the first's completed state instead of redoing the delegation.
        """
        with tempfile.TemporaryDirectory() as tmp:
            memory = LaylaMemoryPolicy(FileMemoryPolicy(Path(tmp)))
            call_count = [0]
            call_lock = threading.Lock()
            real_orchestrator = Orchestrator([_agent("finance-agent", "Finance", "answer")])

            class _SlowCountingOrchestrator:
                def route(self, task):
                    with call_lock:
                        call_count[0] += 1
                    time.sleep(0.05)  # widen the window a racing resume() could exploit
                    return real_orchestrator.route(task)

            tracker = ExecutionTracker(memory)
            runtime = ExecutiveRuntime(
                orchestrator=_SlowCountingOrchestrator(), agent_domains={"finance-agent": "Finance"},
                memory=memory, execution_tracker=tracker,
            )
            from avishkar_layla.types import EXECUTING, Plan

            plan = Plan(id="plan-1", task_id="task-race", steps=(
                PlanStep(id="step-1", required_capability="finance-agent", input="What's the finance ROI?"),
            ))
            task = LaylaTask(input="What's the finance ROI?", id="task-race", state=EXECUTING, plan=plan, plan_id=plan.id)
            runtime.sessions.save(task)

            barrier = threading.Barrier(2)
            results = [None, None]

            def worker(i):
                barrier.wait()
                results[i] = runtime.resume("task-race").state

            threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            self.assertEqual(results, [COMPLETED, COMPLETED])
            self.assertEqual(call_count[0], 1)  # the orchestrator was invoked exactly once


if __name__ == "__main__":
    unittest.main()
