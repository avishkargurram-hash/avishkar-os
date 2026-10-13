import unittest

from avishkar_layla.monitoring import HealthMonitor
from avishkar_layla.notifications import NotificationManager
from avishkar_layla.types import (
    SEVERITY_ACTION_REQUIRED,
    SEVERITY_CRITICAL,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    ApprovalRequest,
    DelegationRecord,
)


class TestNotificationManager(unittest.TestCase):
    def test_pending_returns_all_without_filter(self):
        manager = NotificationManager()
        manager.notify(SEVERITY_INFO, "info msg", "test")
        manager.notify(SEVERITY_CRITICAL, "critical msg", "test")
        self.assertEqual(len(manager.pending()), 2)

    def test_pending_filters_by_min_severity(self):
        manager = NotificationManager()
        manager.notify(SEVERITY_INFO, "info", "test")
        manager.notify(SEVERITY_WARNING, "warn", "test")
        manager.notify(SEVERITY_CRITICAL, "crit", "test")

        result = manager.pending(min_severity=SEVERITY_WARNING)

        self.assertEqual({n.message for n in result}, {"warn", "crit"})

    def test_clear_empties_the_queue(self):
        manager = NotificationManager()
        manager.notify(SEVERITY_INFO, "x", "test")
        manager.clear()
        self.assertEqual(manager.pending(), ())


class TestHealthMonitor(unittest.TestCase):
    def test_failed_delegation_produces_warning(self):
        manager = NotificationManager()
        monitor = HealthMonitor(manager)
        record = DelegationRecord(step_id="s1", agent_name="finance-agent", status="failed", error="boom")

        notification = monitor.observe_delegation(record)

        self.assertIsNotNone(notification)
        self.assertEqual(notification.severity, SEVERITY_WARNING)

    def test_timeout_delegation_produces_action_required(self):
        manager = NotificationManager()
        monitor = HealthMonitor(manager)
        record = DelegationRecord(step_id="s1", agent_name="finance-agent", status="timeout")

        notification = monitor.observe_delegation(record)

        self.assertEqual(notification.severity, SEVERITY_ACTION_REQUIRED)

    def test_completed_delegation_produces_no_notification(self):
        manager = NotificationManager()
        monitor = HealthMonitor(manager)
        record = DelegationRecord(step_id="s1", agent_name="finance-agent", status="completed", output="ok")

        self.assertIsNone(monitor.observe_delegation(record))

    def test_expired_approval_produces_action_required(self):
        manager = NotificationManager()
        monitor = HealthMonitor(manager)
        request = ApprovalRequest(id="a1", task_id="t1", action_description="wire transfer", risk_level="HIGH", status="pending")

        notification = monitor.observe_approval_expired(request)

        self.assertEqual(notification.severity, SEVERITY_ACTION_REQUIRED)

    def test_already_decided_approval_produces_no_notification(self):
        manager = NotificationManager()
        monitor = HealthMonitor(manager)
        request = ApprovalRequest(id="a1", task_id="t1", action_description="x", risk_level="LOW", status="granted")

        self.assertIsNone(monitor.observe_approval_expired(request))


if __name__ == "__main__":
    unittest.main()
