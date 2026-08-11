import unittest

from avishkar_agent import InMemoryMemoryPolicy

from avishkar_layla import LaylaMemoryPolicy
from avishkar_layla.audit import AuditLogger
from avishkar_layla.prediction import PredictionEngine
from avishkar_layla.session import SessionManager
from avishkar_layla.state_machine import StateMachine
from avishkar_layla.types import COMPLETED, REQUIRES_HUMAN, LaylaTask, Plan, PlanStep


def _engine():
    memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
    sessions = SessionManager(memory)
    audit = AuditLogger(memory)
    return PredictionEngine(sessions, audit), sessions, audit


def _completed_task(sessions, task_id, capability):
    plan = Plan(id=f"plan-{task_id}", task_id=task_id, steps=(
        PlanStep(id=f"step-{task_id}", required_capability=capability, input="x"),
    ))
    task = LaylaTask(input="x", id=task_id, state=COMPLETED, plan=plan, plan_id=plan.id)
    sessions.save(task)
    return task


class TestPredictTaskCompletionRisk(unittest.TestCase):
    def test_no_history_returns_none(self):
        engine, sessions, audit = _engine()
        task = LaylaTask(input="x", id="t1")
        sessions.save(task)
        self.assertIsNone(engine.predict_task_completion_risk("t1"))

    def test_unknown_task_returns_none(self):
        engine, sessions, audit = _engine()
        self.assertIsNone(engine.predict_task_completion_risk("never-existed"))

    def test_all_successful_delegations_gives_zero_risk_and_real_confidence(self):
        engine, sessions, audit = _engine()
        sessions.save(LaylaTask(input="x", id="t1"))
        for _ in range(3):
            audit.record("layla.delegation.completed", {}, task_id="t1")

        prediction = engine.predict_task_completion_risk("t1")

        self.assertIn("0%", prediction.prediction)
        self.assertAlmostEqual(prediction.confidence, 3 / 5.0)
        self.assertEqual(prediction.evidence["failures"], 0)

    def test_failures_produce_a_nonzero_risk_ratio(self):
        engine, sessions, audit = _engine()
        sessions.save(LaylaTask(input="x", id="t1"))
        audit.record("layla.delegation.completed", {}, task_id="t1")
        audit.record("layla.delegation.failed", {}, task_id="t1")

        prediction = engine.predict_task_completion_risk("t1")

        self.assertEqual(prediction.evidence["failures"], 1)
        self.assertEqual(prediction.evidence["delegation_attempts"], 2)
        self.assertIn("review", prediction.recommended_action.lower())

    def test_confidence_caps_at_one(self):
        engine, sessions, audit = _engine()
        sessions.save(LaylaTask(input="x", id="t1"))
        for _ in range(10):
            audit.record("layla.delegation.completed", {}, task_id="t1")

        prediction = engine.predict_task_completion_risk("t1")
        self.assertEqual(prediction.confidence, 1.0)


class TestPredictNextCapability(unittest.TestCase):
    def test_no_completed_tasks_returns_none(self):
        engine, sessions, audit = _engine()
        self.assertIsNone(engine.predict_next_capability())

    def test_most_frequent_capability_wins_with_real_frequency_confidence(self):
        engine, sessions, audit = _engine()
        _completed_task(sessions, "t1", "finance-agent")
        _completed_task(sessions, "t2", "finance-agent")
        _completed_task(sessions, "t3", "legal-agent")

        prediction = engine.predict_next_capability()

        self.assertIn("finance-agent", prediction.prediction)
        self.assertAlmostEqual(prediction.confidence, 2 / 3.0)
        self.assertEqual(prediction.evidence["capability_counts"], {"finance-agent": 2, "legal-agent": 1})

    def test_incomplete_tasks_are_not_counted(self):
        engine, sessions, audit = _engine()
        plan = Plan(id="plan-t1", task_id="t1", steps=(PlanStep(id="s1", required_capability="finance-agent", input="x"),))
        sm = StateMachine()
        task = LaylaTask(input="x", id="t1", plan=plan)
        sm.transition(task, "UNDERSTANDING")
        sessions.save(task)  # not COMPLETED

        self.assertIsNone(engine.predict_next_capability())


class TestPredictStuckTaskRisk(unittest.TestCase):
    def test_no_tasks_returns_empty(self):
        engine, sessions, audit = _engine()
        self.assertEqual(engine.predict_stuck_task_risk(), ())

    def test_all_completed_returns_empty(self):
        engine, sessions, audit = _engine()
        _completed_task(sessions, "t1", "finance-agent")
        self.assertEqual(engine.predict_stuck_task_risk(), ())

    def test_mixed_completion_produces_a_real_ratio(self):
        engine, sessions, audit = _engine()
        _completed_task(sessions, "t1", "finance-agent")
        sm = StateMachine()
        stuck = LaylaTask(input="x", id="t2")
        sm.transition(stuck, "UNDERSTANDING")
        sessions.save(stuck)

        predictions = engine.predict_stuck_task_risk()

        self.assertEqual(len(predictions), 1)
        self.assertIn("t2", predictions[0].evidence["incomplete_task_ids"])
        self.assertAlmostEqual(predictions[0].confidence, 2 / 5.0)


if __name__ == "__main__":
    unittest.main()
