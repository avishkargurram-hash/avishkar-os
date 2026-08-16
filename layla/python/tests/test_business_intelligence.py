import unittest

from avishkar_agent import InMemoryMemoryPolicy

from avishkar_layla import LaylaMemoryPolicy
from avishkar_layla.audit import AuditLogger
from avishkar_layla.business_intelligence import BusinessIntelligenceEngine
from avishkar_layla.session import SessionManager
from avishkar_layla.types import COMPLETED, REQUIRES_HUMAN, LaylaTask, Plan, PlanStep


def _engine():
    memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
    return BusinessIntelligenceEngine(SessionManager(memory), AuditLogger(memory)), SessionManager(memory), AuditLogger(memory)


class TestBusinessIntelligenceEmpty(unittest.TestCase):
    def test_no_tasks_produces_an_honest_empty_report(self):
        engine, sessions, audit = _engine()
        report = engine.generate_report()

        self.assertEqual(report.total_tasks, 0)
        self.assertEqual(report.total_cost_usd, 0.0)
        self.assertIn("No tasks recorded yet", engine.summary())


class TestBusinessIntelligenceRealAggregation(unittest.TestCase):
    def test_task_counts_and_cost_are_real_sums(self):
        memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        sessions = SessionManager(memory)
        audit = AuditLogger(memory)
        engine = BusinessIntelligenceEngine(sessions, audit)

        plan = Plan(id="p1", task_id="t1", steps=(PlanStep(id="s1", required_capability="finance-agent", input="x"),))
        completed = LaylaTask(input="x", id="t1", state=COMPLETED, plan=plan, plan_id=plan.id)
        sessions.save(completed)
        audit.record("layla.delegation.completed", {"step_id": "s1", "cost_usd": 0.0042}, task_id="t1")

        stuck = LaylaTask(input="y", id="t2", state=REQUIRES_HUMAN)
        sessions.save(stuck)

        report = engine.generate_report()

        self.assertEqual(report.total_tasks, 2)
        self.assertEqual(report.completed_count, 1)
        self.assertEqual(report.incomplete_count, 1)
        self.assertAlmostEqual(report.total_cost_usd, 0.0042)
        self.assertEqual(report.delegation_success_rate_by_capability["finance-agent"], 1.0)

    def test_failed_delegation_lowers_the_real_success_rate(self):
        memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        sessions = SessionManager(memory)
        audit = AuditLogger(memory)
        engine = BusinessIntelligenceEngine(sessions, audit)

        plan1 = Plan(id="p1", task_id="t1", steps=(PlanStep(id="s1", required_capability="finance-agent", input="x"),))
        sessions.save(LaylaTask(input="x", id="t1", state=COMPLETED, plan=plan1, plan_id=plan1.id))
        audit.record("layla.delegation.completed", {"step_id": "s1", "cost_usd": 0.0}, task_id="t1")

        plan2 = Plan(id="p2", task_id="t2", steps=(PlanStep(id="s2", required_capability="finance-agent", input="y"),))
        sessions.save(LaylaTask(input="y", id="t2", state=REQUIRES_HUMAN, plan=plan2, plan_id=plan2.id))
        audit.record("layla.delegation.failed", {"step_id": "s2", "cost_usd": 0.0}, task_id="t2")

        report = engine.generate_report()

        self.assertEqual(report.delegation_success_rate_by_capability["finance-agent"], 0.5)
        self.assertIn("50%", engine.summary())


if __name__ == "__main__":
    unittest.main()
