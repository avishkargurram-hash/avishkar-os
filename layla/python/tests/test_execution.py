import unittest

from avishkar_agent import InMemoryMemoryPolicy

from avishkar_layla import IdempotencyConflictError, LaylaMemoryPolicy
from avishkar_layla.execution import (
    EXEC_COMPLETED,
    EXEC_EXECUTING,
    EXEC_FAILED,
    EXEC_REQUESTED,
    EXEC_UNKNOWN,
    OP_HIGH_RISK,
    OP_READ,
    OP_WRITE,
    ExecutionTracker,
    classify_operation,
)


class TestClassifyOperation(unittest.TestCase):
    def test_read_verbs(self):
        self.assertEqual(classify_operation("search recent AI funding news"), OP_READ)
        self.assertEqual(classify_operation("inspect this repository for issues"), OP_READ)

    def test_write_verbs(self):
        self.assertEqual(classify_operation("send an email to the team"), OP_WRITE)
        self.assertEqual(classify_operation("create a GitHub issue for this bug"), OP_WRITE)
        self.assertEqual(classify_operation("delete the old branch"), OP_WRITE)

    def test_high_risk_verbs(self):
        self.assertEqual(classify_operation("initiate a financial transaction"), OP_HIGH_RISK)
        self.assertEqual(classify_operation("sign the contract with the vendor"), OP_HIGH_RISK)

    def test_unrecognized_text_defaults_to_write_fail_closed(self):
        self.assertEqual(classify_operation("do the thing with the widget"), OP_WRITE)


class TestExecutionTrackerLifecycle(unittest.TestCase):
    def _tracker(self):
        return ExecutionTracker(LaylaMemoryPolicy(InMemoryMemoryPolicy()), clock=lambda: 0.0)

    def test_begin_creates_a_requested_record(self):
        tracker = self._tracker()
        record = tracker.begin("key-1", OP_WRITE, "send an email")
        self.assertEqual(record.status, EXEC_REQUESTED)
        self.assertEqual(record.operation_kind, OP_WRITE)

    def test_begin_is_idempotent_returns_existing_record_unchanged(self):
        tracker = self._tracker()
        tracker.begin("key-1", OP_WRITE, "send an email")
        tracker.transition("key-1", EXEC_EXECUTING)

        second = tracker.begin("key-1", OP_WRITE, "send an email")

        self.assertEqual(second.status, EXEC_EXECUTING)  # not reset to REQUESTED

    def test_transition_updates_status_result_and_attempts(self):
        tracker = self._tracker()
        tracker.begin("key-1", OP_WRITE, "send an email")

        completed = tracker.transition("key-1", EXEC_COMPLETED, result={"message_id": "abc"}, increment_attempts=True)

        self.assertEqual(completed.status, EXEC_COMPLETED)
        self.assertEqual(completed.result, {"message_id": "abc"})
        self.assertEqual(completed.attempts, 1)

    def test_transition_unknown_key_raises(self):
        tracker = self._tracker()
        with self.assertRaises(KeyError):
            tracker.transition("never-began", EXEC_COMPLETED)

    def test_get_missing_key_returns_none(self):
        tracker = self._tracker()
        self.assertIsNone(tracker.get("never-began"))

    def test_begin_with_mismatched_description_raises_idempotency_conflict(self):
        tracker = self._tracker()
        tracker.begin("key-1", OP_WRITE, "send an email to finance")

        with self.assertRaises(IdempotencyConflictError):
            tracker.begin("key-1", OP_WRITE, "send an email to legal")  # same key, different operation

    def test_begin_with_matching_description_is_not_a_conflict(self):
        tracker = self._tracker()
        first = tracker.begin("key-1", OP_WRITE, "send an email to finance")

        second = tracker.begin("key-1", OP_WRITE, "send an email to finance")  # a genuine retry

        self.assertEqual(second.status, first.status)


class TestResolveUnknown(unittest.TestCase):
    def test_resolve_unknown_to_completed(self):
        tracker = ExecutionTracker(LaylaMemoryPolicy(InMemoryMemoryPolicy()), clock=lambda: 0.0)
        tracker.begin("key-1", OP_WRITE, "send an email")
        tracker.transition("key-1", EXEC_UNKNOWN, error="timeout, outcome uncertain")

        resolved = tracker.resolve_unknown("key-1", EXEC_COMPLETED, note="confirmed sent via provider dashboard")

        self.assertEqual(resolved.status, EXEC_COMPLETED)

    def test_resolve_unknown_to_failed_allows_future_retry(self):
        tracker = ExecutionTracker(LaylaMemoryPolicy(InMemoryMemoryPolicy()), clock=lambda: 0.0)
        tracker.begin("key-1", OP_WRITE, "send an email")
        tracker.transition("key-1", EXEC_UNKNOWN)

        resolved = tracker.resolve_unknown("key-1", EXEC_FAILED, note="confirmed never sent")

        self.assertEqual(resolved.status, EXEC_FAILED)

    def test_resolve_unknown_refuses_non_unknown_record(self):
        tracker = ExecutionTracker(LaylaMemoryPolicy(InMemoryMemoryPolicy()), clock=lambda: 0.0)
        tracker.begin("key-1", OP_WRITE, "send an email")
        tracker.transition("key-1", EXEC_COMPLETED, result={"ok": True})

        with self.assertRaises(ValueError):
            tracker.resolve_unknown("key-1", EXEC_FAILED)


if __name__ == "__main__":
    unittest.main()
