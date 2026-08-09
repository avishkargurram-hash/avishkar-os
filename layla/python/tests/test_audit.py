import unittest

from avishkar_agent import InMemoryMemoryPolicy

from avishkar_layla import LaylaMemoryPolicy
from avishkar_layla.audit import AuditLogger


class TestAuditLogger(unittest.TestCase):
    def test_record_and_history_round_trip(self):
        logger = AuditLogger(LaylaMemoryPolicy(InMemoryMemoryPolicy()))
        logger.record("layla.task.received", {"input": "do the thing"}, task_id="t1")
        logger.record("layla.plan.created", {"plan_id": "p1"}, task_id="t1")

        history = logger.history("t1")

        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].event_type, "layla.task.received")
        self.assertEqual(history[1].event_type, "layla.plan.created")

    def test_different_tasks_have_independent_history(self):
        logger = AuditLogger(LaylaMemoryPolicy(InMemoryMemoryPolicy()))
        logger.record("event-a", {}, task_id="t1")
        logger.record("event-b", {}, task_id="t2")

        self.assertEqual(len(logger.history("t1")), 1)
        self.assertEqual(len(logger.history("t2")), 1)

    def test_no_task_id_uses_system_scope(self):
        logger = AuditLogger(LaylaMemoryPolicy(InMemoryMemoryPolicy()))
        logger.record("system.startup", {})
        self.assertEqual(len(logger.history()), 1)

    def test_unknown_task_returns_empty_history(self):
        logger = AuditLogger(LaylaMemoryPolicy(InMemoryMemoryPolicy()))
        self.assertEqual(logger.history("never-seen"), ())

    def test_never_stores_a_thinking_trace_field(self):
        # Structured fields only -- payload is whatever the caller
        # passes, but this test documents the discipline: callers pass
        # structured summaries (plan_id, delegation status), not raw
        # model reasoning text, per Part XV.
        logger = AuditLogger(LaylaMemoryPolicy(InMemoryMemoryPolicy()))
        record = logger.record("layla.delegation.completed", {"agent_name": "finance-agent", "status": "completed"}, task_id="t1")
        self.assertNotIn("thinking_trace", record.payload)
        self.assertNotIn("chain_of_thought", record.payload)


if __name__ == "__main__":
    unittest.main()
