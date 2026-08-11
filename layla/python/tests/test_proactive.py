import unittest

from avishkar_agent import InMemoryMemoryPolicy

from avishkar_layla import LaylaMemoryPolicy
from avishkar_layla.audit import AuditLogger
from avishkar_layla.notifications import NotificationManager
from avishkar_layla.proactive import (
    ACTION_ACT,
    ACTION_IGNORE,
    ACTION_OBSERVE,
    ACTION_SUGGEST,
    ACTION_URGENTLY_ALERT,
    ProactiveEngine,
    ProactiveTrigger,
)
from avishkar_layla.session import SessionManager
from avishkar_layla.state_machine import StateMachine
from avishkar_layla.types import REQUIRES_HUMAN, SEVERITY_ACTION_REQUIRED, SEVERITY_CRITICAL, LaylaTask


def _engine(memory=None, **kwargs):
    memory = memory or LaylaMemoryPolicy(InMemoryMemoryPolicy())
    sessions = SessionManager(memory)
    audit = AuditLogger(memory)
    notifications = NotificationManager()
    return ProactiveEngine(sessions, audit, notifications, **kwargs), sessions, audit, notifications


def _stuck_task(sessions, *, task_id="t1", blocked_reason="capability denied"):
    task = LaylaTask(input="do something", id=task_id)
    sm = StateMachine()
    sm.transition(task, "UNDERSTANDING")
    for state in ("CONTEXT_LOADING", "PLANNING", REQUIRES_HUMAN):
        sm.transition(task, state)
    task.blocked_reason = blocked_reason
    sessions.save(task)
    return task


class TestProactiveEngineNoTriggers(unittest.TestCase):
    def test_no_incomplete_tasks_means_no_triggers(self):
        engine, _, _, _ = _engine()
        self.assertEqual(engine.evaluate(), ())

    def test_a_freshly_stuck_task_is_below_threshold_and_produces_nothing(self):
        engine, sessions, _, notifications = _engine(clock=lambda: 1000.0)
        _stuck_task(sessions)

        triggers = engine.evaluate()

        self.assertEqual(triggers, ())
        self.assertEqual(notifications.pending(), ())


class TestProactiveEngineStuckTaskEscalation(unittest.TestCase):
    def test_stuck_task_past_suggest_threshold_notifies(self):
        # transition happens "at" real wall-clock time; simulate a
        # clock far enough in the future that age_seconds crosses the
        # suggest threshold (default 3600s).
        real_now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).timestamp()
        engine, sessions, audit, notifications = _engine(
            clock=lambda: real_now + 7200, stuck_suggest_seconds=3600.0, stuck_alert_seconds=86400.0,
        )
        task = _stuck_task(sessions)

        triggers = engine.evaluate()

        self.assertEqual(len(triggers), 1)
        self.assertEqual(triggers[0].action_level, ACTION_SUGGEST)
        self.assertEqual(triggers[0].task_id, task.id)
        pending = notifications.pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].severity, SEVERITY_ACTION_REQUIRED)
        history = audit.history(task_id=task.id)
        self.assertTrue(any(r.event_type == "layla.proactive.suggested" for r in history))

    def test_stuck_task_past_alert_threshold_urgently_alerts(self):
        real_now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).timestamp()
        engine, sessions, audit, notifications = _engine(
            clock=lambda: real_now + 200000, stuck_suggest_seconds=3600.0, stuck_alert_seconds=86400.0,
        )
        _stuck_task(sessions)

        triggers = engine.evaluate()

        self.assertEqual(triggers[0].action_level, ACTION_URGENTLY_ALERT)
        self.assertEqual(notifications.pending()[0].severity, SEVERITY_CRITICAL)


class TestProactiveEngineRepeatedFailures(unittest.TestCase):
    def test_two_failures_is_observe_only_no_notification(self):
        engine, sessions, audit, notifications = _engine(failure_observe_threshold=2, failure_suggest_threshold=3)
        task = _stuck_task(sessions, task_id="t-fail")
        audit.record("layla.delegation.failed", {"step_id": "s1"}, task_id=task.id)
        audit.record("layla.delegation.failed", {"step_id": "s2"}, task_id=task.id)

        triggers = engine.evaluate()

        levels = {t.source: t.action_level for t in triggers}
        self.assertEqual(levels.get("proactive.repeated_failures"), ACTION_OBSERVE)
        self.assertEqual(notifications.pending(), ())  # OBSERVE never notifies

    def test_three_failures_escalates_to_suggest(self):
        engine, sessions, audit, notifications = _engine(failure_observe_threshold=2, failure_suggest_threshold=3)
        task = _stuck_task(sessions, task_id="t-fail")
        for i in range(3):
            audit.record("layla.delegation.failed", {"step_id": f"s{i}"}, task_id=task.id)

        triggers = engine.evaluate()

        levels = {t.source: t.action_level for t in triggers}
        self.assertEqual(levels.get("proactive.repeated_failures"), ACTION_SUGGEST)
        self.assertTrue(any(n.source == "proactive.repeated_failures" for n in notifications.pending()))


class TestProactiveEngineActDispatch(unittest.TestCase):
    def test_act_trigger_invokes_the_callback(self):
        calls = []

        def _custom_evaluator(self):
            return (ProactiveTrigger(
                id="custom-1", action_level=ACTION_ACT, description="do the thing",
                evidence={"reason": "test"}, source="test.custom",
            ),)

        engine, sessions, audit, notifications = _engine(
            act_callback=lambda trigger: calls.append(trigger), extra_evaluators=(_custom_evaluator,),
        )

        engine.evaluate()

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].id, "custom-1")
        history = audit.history(task_id=None)
        self.assertTrue(any(r.event_type == "layla.proactive.act_triggered" for r in history))

    def test_act_trigger_without_a_callback_is_a_safe_no_op(self):
        """No callback wired means no autonomous action is possible --
        a deliberate fail-safe, not a crash (module docstring)."""
        def _custom_evaluator(self):
            return (ProactiveTrigger(
                id="custom-2", action_level=ACTION_ACT, description="do the thing",
                evidence={}, source="test.custom",
            ),)

        engine, sessions, audit, notifications = _engine(extra_evaluators=(_custom_evaluator,))

        triggers = engine.evaluate()  # must not raise

        self.assertEqual(len(triggers), 1)
        history = audit.history(task_id=None)
        self.assertTrue(any(
            r.event_type == "layla.proactive.act_triggered" and r.payload["callback_wired"] is False
            for r in history
        ))


class TestProactiveEngineIgnoreIsSilent(unittest.TestCase):
    def test_ignore_level_produces_no_audit_or_notification(self):
        def _ignoring_evaluator(self):
            return (ProactiveTrigger(
                id="noop", action_level=ACTION_IGNORE, description="nothing to see here",
                evidence={}, source="test.ignore",
            ),)

        engine, sessions, audit, notifications = _engine(extra_evaluators=(_ignoring_evaluator,))

        triggers = engine.evaluate()

        self.assertEqual(len(triggers), 1)  # returned to the caller for inspection
        self.assertEqual(notifications.pending(), ())
        self.assertEqual(audit.history(task_id=None), ())  # but never recorded -- no noise


if __name__ == "__main__":
    unittest.main()
