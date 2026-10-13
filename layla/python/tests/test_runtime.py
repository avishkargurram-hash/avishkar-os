import unittest

from avishkar_agent import (
    AgentBlueprint,
    ApprovalGate,
    ChiefDomainAgent,
    InMemoryMemoryPolicy,
    Orchestrator,
    ToolRegistry,
)
from avishkar_agent.thinking import DEFAULT_THINKING_MODELS
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router

from avishkar_layla import LaylaMemoryPolicy
from avishkar_layla.runtime import ExecutiveRuntime
from avishkar_layla.scheduler import Scheduler
from avishkar_layla.types import COMPLETED, REQUIRES_HUMAN


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


def _runtime(agents, *, approval_gate=None):
    orchestrator = Orchestrator(list(agents))
    agent_domains = {a.name: a.domain for a in agents}
    memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
    return ExecutiveRuntime(
        orchestrator=orchestrator, agent_domains=agent_domains, memory=memory,
        approval_gate=approval_gate, clock=lambda: 0.0, sleep_fn=lambda s: None,
    )


class TestExecutiveRuntimeHappyPath(unittest.TestCase):
    def test_low_risk_single_agent_task_completes(self):
        runtime = _runtime([_agent("finance-agent", "Finance", "the ROI looks positive")])

        task = runtime.handle_event("What's the projected ROI, from a finance perspective?")

        self.assertEqual(task.state, COMPLETED)
        self.assertIn("the ROI looks positive", task.result)

    def test_audit_trail_is_recorded(self):
        runtime = _runtime([_agent("finance-agent", "Finance", "answer")])
        task = runtime.handle_event("What's the projected finance ROI?")

        history = runtime.audit.history(task.id)

        event_types = [record.event_type for record in history]
        self.assertIn("layla.task.received", event_types)
        self.assertIn("layla.plan.created", event_types)
        self.assertIn("layla.task.completed", event_types)

    def test_completed_task_is_persisted_in_session_store(self):
        runtime = _runtime([_agent("finance-agent", "Finance", "answer")])
        task = runtime.handle_event("What's the finance ROI?")

        loaded = runtime.sessions.load(task.id)

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.state, COMPLETED)


class TestExecutiveRuntimeUnknownCapability(unittest.TestCase):
    def test_unrecognized_request_requires_human(self):
        runtime = _runtime([_agent("finance-agent", "Finance", "x")])

        task = runtime.handle_event("something with absolutely no matching domain keywords zz")

        self.assertEqual(task.state, REQUIRES_HUMAN)
        self.assertIsNotNone(task.blocked_reason)


class TestExecutiveRuntimeApproval(unittest.TestCase):
    def test_high_risk_task_denied_by_gate_requires_human(self):
        gate = ApprovalGate(policy="always_ask", callback=lambda task: False)
        runtime = _runtime([_agent("finance-agent", "Finance", "x")], approval_gate=gate)

        task = runtime.handle_event("initiate a wire transfer for the finance team")

        self.assertEqual(task.state, REQUIRES_HUMAN)

    def test_high_risk_task_granted_by_gate_completes(self):
        gate = ApprovalGate(policy="always_allow")
        runtime = _runtime([_agent("finance-agent", "Finance", "transfer processed")], approval_gate=gate)

        task = runtime.handle_event("initiate a wire transfer for the finance team")

        self.assertEqual(task.state, COMPLETED)


class TestExecutiveRuntimeConflict(unittest.TestCase):
    def test_disagreeing_agents_require_human(self):
        legal = _agent("legal-agent", "Legal & Compliance", "This contract carries significant liability risk.")
        finance = _agent("finance-agent", "Finance & Economics", "Preheat the oven to 350 degrees before baking.")
        runtime = _runtime([legal, finance])

        task = runtime.handle_event("Review this from a legal and finance perspective.")

        self.assertEqual(task.state, REQUIRES_HUMAN)
        self.assertIn("conflict", task.blocked_reason.lower())


class TestExecutiveRuntimeScheduler(unittest.TestCase):
    def test_run_forever_ticks_scheduler_and_returns_iteration_count(self):
        scheduler = Scheduler(clock=lambda: 0.0)
        calls = []
        scheduler.schedule_once(0.0, lambda: calls.append(1))

        orchestrator = Orchestrator([_agent("finance-agent", "Finance", "x")])
        memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        runtime = ExecutiveRuntime(
            orchestrator=orchestrator, agent_domains={"finance-agent": "Finance"}, memory=memory,
            scheduler=scheduler, sleep_fn=lambda s: None,
        )

        iterations = runtime.run_forever(max_iterations=3, tick_interval_seconds=0.0)

        self.assertEqual(iterations, 3)
        self.assertEqual(calls, [1])  # one-shot job fires once, not on every tick


class TestExecutiveRuntimeGracefulShutdownAndHeartbeat(unittest.TestCase):
    """Directive D Part XI (ADR-0038): real graceful shutdown and a
    real heartbeat for the 24/7 run_forever() loop.
    """

    def _runtime(self, *, clock=lambda: 100.0):
        orchestrator = Orchestrator([_agent("finance-agent", "Finance", "x")])
        memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        return ExecutiveRuntime(
            orchestrator=orchestrator, agent_domains={"finance-agent": "Finance"}, memory=memory,
            sleep_fn=lambda s: None, clock=clock,
        ), memory

    def test_request_shutdown_stops_the_loop_before_max_iterations(self):
        runtime, _ = self._runtime()

        # request_shutdown() simulates an external signal handler
        # firing -- called directly here (before run_forever(), for a
        # deterministic single-threaded test) rather than from a real
        # second thread mid-run.
        runtime.request_shutdown()
        iterations = runtime.run_forever(max_iterations=10, tick_interval_seconds=0.0)

        self.assertEqual(iterations, 0)  # shutdown was already requested before the first tick

    def test_shutdown_flag_is_cleared_after_run_forever_returns(self):
        """A second real run_forever() call must not immediately stop
        again just because a previous run was shut down.
        """
        runtime, _ = self._runtime()
        runtime.request_shutdown()
        runtime.run_forever(max_iterations=10, tick_interval_seconds=0.0)

        iterations = runtime.run_forever(max_iterations=3, tick_interval_seconds=0.0)
        self.assertEqual(iterations, 3)

    def test_last_tick_at_is_none_before_run_forever_ever_completes_an_iteration(self):
        runtime, _ = self._runtime()
        self.assertIsNone(runtime.last_tick_at)

    def test_last_tick_at_reflects_the_real_injected_clock(self):
        clock = [100.0]
        runtime, _ = self._runtime(clock=lambda: clock[0])

        runtime.run_forever(max_iterations=1, tick_interval_seconds=0.0)

        self.assertEqual(runtime.last_tick_at, 100.0)

    def test_is_alive_is_false_before_any_run(self):
        runtime, _ = self._runtime()
        self.assertFalse(runtime.is_alive(max_staleness_seconds=60.0))

    def test_is_alive_is_true_shortly_after_a_real_tick(self):
        clock = [100.0]
        runtime, _ = self._runtime(clock=lambda: clock[0])
        runtime.run_forever(max_iterations=1, tick_interval_seconds=0.0)

        self.assertTrue(runtime.is_alive(max_staleness_seconds=60.0, now=110.0))

    def test_is_alive_is_false_once_the_tick_is_stale(self):
        clock = [100.0]
        runtime, _ = self._runtime(clock=lambda: clock[0])
        runtime.run_forever(max_iterations=1, tick_interval_seconds=0.0)

        self.assertFalse(runtime.is_alive(max_staleness_seconds=60.0, now=200.0))

    def test_run_forever_records_real_start_and_stop_audit_events(self):
        runtime, _ = self._runtime()
        runtime.run_forever(max_iterations=2, tick_interval_seconds=0.0)

        history = runtime.audit.history()  # real AuditLogger.history(), system-scoped (no task_id)
        event_types = [record.event_type for record in history]

        self.assertIn("layla.runtime.run_forever_started", event_types)
        self.assertIn("layla.runtime.run_forever_stopped", event_types)
        stopped = next(r for r in history if r.event_type == "layla.runtime.run_forever_stopped")
        self.assertEqual(stopped.payload["iterations"], 2)

    def test_operational_health_before_any_run_reports_not_alive_and_zero_incomplete_tasks(self):
        runtime, _ = self._runtime()
        report = runtime.operational_health()

        self.assertFalse(report["alive"])
        self.assertIsNone(report["last_tick_at"])
        self.assertEqual(report["incomplete_task_count"], 0)

    def test_operational_health_reflects_a_real_tick(self):
        clock = [100.0]
        runtime, _ = self._runtime(clock=lambda: clock[0])
        runtime.run_forever(max_iterations=1, tick_interval_seconds=0.0)

        report = runtime.operational_health(max_staleness_seconds=60.0)

        self.assertTrue(report["alive"])
        self.assertEqual(report["last_tick_at"], 100.0)

    def test_operational_health_includes_real_scheduler_state_when_configured(self):
        scheduler = Scheduler(clock=lambda: 0.0, max_consecutive_failures=1)

        def _boom():
            raise RuntimeError("boom")

        scheduler.schedule_recurring(1.0, _boom, start_at=1.0)
        scheduler.schedule_once(100.0, lambda: None)
        scheduler.tick(now=1.0)  # dead-letters the failing job

        orchestrator = Orchestrator([_agent("finance-agent", "Finance", "x")])
        memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        runtime = ExecutiveRuntime(
            orchestrator=orchestrator, agent_domains={"finance-agent": "Finance"}, memory=memory,
            scheduler=scheduler, sleep_fn=lambda s: None,
        )

        report = runtime.operational_health()

        self.assertEqual(report["scheduler_pending_job_count"], 1)  # only the still-pending one-shot job
        self.assertEqual(len(report["scheduler_dead_lettered_jobs"]), 1)

    def test_operational_health_omits_scheduler_fields_when_no_scheduler_configured(self):
        runtime, _ = self._runtime()
        report = runtime.operational_health()
        self.assertNotIn("scheduler_pending_job_count", report)


if __name__ == "__main__":
    unittest.main()
