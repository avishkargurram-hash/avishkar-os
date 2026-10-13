import unittest

from avishkar_agent import AgentBlueprint, ChiefDomainAgent, InMemoryMemoryPolicy, Orchestrator, ToolRegistry
from avishkar_agent.thinking import DEFAULT_THINKING_MODELS
from avishkar_router import ModelSpec, MockProvider, Router, RoutingPolicy

from avishkar_layla import LaylaMemoryPolicy
from avishkar_layla.business_intelligence import BusinessIntelligenceEngine
from avishkar_layla.observability import build_production_health_report
from avishkar_layla.runtime import ExecutiveRuntime
from avishkar_layla.session import SessionManager
from avishkar_layla.types import LaylaTask, Plan, PlanStep


def _agent(name, domain, response_text):
    blueprint = AgentBlueprint(name=name, domain=domain, version="0.1.0", mission="test", default_model="mock-fast")
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat",),
                           input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text=response_text,
    )
    router = Router([provider], RoutingPolicy(default_model="mock-fast"))
    return ChiefDomainAgent(blueprint, router, InMemoryMemoryPolicy(), ToolRegistry(), DEFAULT_THINKING_MODELS)


def _runtime():
    orchestrator = Orchestrator([_agent("finance-agent", "Finance", "x")])
    memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
    runtime = ExecutiveRuntime(
        orchestrator=orchestrator, agent_domains={"finance-agent": "Finance"}, memory=memory,
        sleep_fn=lambda s: None,
    )
    return runtime, memory


def _record_delegation(runtime, task_id, step_id, event_suffix, **extra_payload):
    """Real usage requires both a saved LaylaTask AND its audit
    record -- `AuditLogger.history()` is scoped per task_id, and
    `build_production_health_report()` discovers task ids via
    `SessionManager.list_all()`, the same real pattern
    `BusinessIntelligenceEngine.generate_report()` already uses.
    """
    plan = Plan(id=f"plan-{task_id}", task_id=task_id, steps=(PlanStep(id=step_id, required_capability="finance-agent", input="x"),))
    task = LaylaTask(input="x", id=task_id, plan=plan, plan_id=plan.id)
    runtime.sessions.save(task)
    runtime.audit.record(f"layla.delegation.{event_suffix}", {"step_id": step_id, **extra_payload}, task_id=task_id)


class TestProductionHealthReportBasic(unittest.TestCase):
    def test_report_includes_real_operational_health(self):
        runtime, _ = _runtime()
        runtime.run_forever(max_iterations=1, tick_interval_seconds=0.0)

        report = build_production_health_report(runtime)

        self.assertTrue(report.operational["alive"])
        self.assertIsNotNone(report.generated_at)

    def test_no_delegation_history_gives_zero_failure_rate(self):
        runtime, _ = _runtime()
        report = build_production_health_report(runtime)

        self.assertEqual(report.delegation_failure_rate, 0.0)
        self.assertEqual(sum(report.delegation_totals.values()), 0)

    def test_business_intelligence_omitted_when_not_provided(self):
        runtime, _ = _runtime()
        report = build_production_health_report(runtime)
        self.assertIsNone(report.business_intelligence)


class TestProductionHealthReportDelegationRates(unittest.TestCase):
    def test_real_failure_rate_computed_from_real_audit_history(self):
        runtime, _ = _runtime()
        _record_delegation(runtime, "t1", "s1", "completed")
        _record_delegation(runtime, "t2", "s2", "completed")
        _record_delegation(runtime, "t3", "s3", "failed")
        _record_delegation(runtime, "t4", "s4", "timeout")

        report = build_production_health_report(runtime)

        self.assertEqual(report.delegation_totals["completed"], 2)
        self.assertEqual(report.delegation_totals["failed"], 1)
        self.assertEqual(report.delegation_totals["timeout"], 1)
        self.assertAlmostEqual(report.delegation_failure_rate, 2 / 4)

    def test_denied_delegations_count_toward_failure_rate(self):
        runtime, _ = _runtime()
        _record_delegation(runtime, "t1", "s1", "completed")
        _record_delegation(runtime, "t2", "s2", "denied")

        report = build_production_health_report(runtime)
        self.assertAlmostEqual(report.delegation_failure_rate, 0.5)

    def test_non_delegation_audit_events_are_ignored(self):
        runtime, _ = _runtime()
        task = LaylaTask(input="x", id="t1")
        runtime.sessions.save(task)
        runtime.audit.record("layla.proactive.observed", {"trigger_id": "x"}, task_id="t1")
        runtime.audit.record("layla.robotics.emergency_stop", {"reason": "test"}, task_id="t1")

        report = build_production_health_report(runtime)
        self.assertEqual(sum(report.delegation_totals.values()), 0)


class TestProductionHealthReportBusinessIntelligence(unittest.TestCase):
    def test_business_intelligence_is_folded_in_via_its_own_real_report(self):
        runtime, memory = _runtime()
        sessions = SessionManager(memory)
        bi = BusinessIntelligenceEngine(sessions, runtime.audit)

        _record_delegation(runtime, "t1", "s1", "completed", cost_usd=0.05)

        report = build_production_health_report(runtime, business_intelligence=bi)

        self.assertIsNotNone(report.business_intelligence)
        self.assertEqual(report.business_intelligence["total_cost_usd"], 0.05)


if __name__ == "__main__":
    unittest.main()
