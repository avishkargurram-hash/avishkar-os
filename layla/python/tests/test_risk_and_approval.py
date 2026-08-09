import unittest

from avishkar_agent import ApprovalGate

from avishkar_layla import RISK_HIGH, RISK_LOW, RISK_MEDIUM
from avishkar_layla.approval import ApprovalManager
from avishkar_layla.errors import ApprovalDeniedError, ApprovalExpiredError
from avishkar_layla.risk import classify_risk


class TestClassifyRisk(unittest.TestCase):
    def test_low_risk_default(self):
        self.assertEqual(classify_risk("summarize this document"), RISK_LOW)

    def test_medium_risk_calendar(self):
        self.assertEqual(classify_risk("create a calendar event for Friday"), RISK_MEDIUM)

    def test_high_risk_financial(self):
        self.assertEqual(classify_risk("initiate a wire transfer to the vendor"), RISK_HIGH)

    def test_high_risk_destructive_repo_action(self):
        self.assertEqual(classify_risk("force push to main to fix the branch"), RISK_HIGH)

    def test_high_risk_production_deploy(self):
        self.assertEqual(classify_risk("deploy to production now"), RISK_HIGH)


class TestApprovalManagerAutoGrant(unittest.TestCase):
    def test_low_risk_auto_grants(self):
        manager = ApprovalManager()
        request = manager.request("task-1", "organize notes", RISK_LOW)
        self.assertEqual(request.status, "granted")
        self.assertTrue(request.auto)
        self.assertEqual(manager.check(request.id), "granted")


class TestApprovalManagerWithGate(unittest.TestCase):
    def test_gate_grants_medium_risk(self):
        gate = ApprovalGate(policy="always_allow")
        manager = ApprovalManager(approval_gate=gate)
        request = manager.request("task-1", "send a routine status email", RISK_MEDIUM)
        self.assertEqual(request.status, "granted")

    def test_gate_denies_high_risk(self):
        gate = ApprovalGate(policy="always_ask", callback=lambda task: False)
        manager = ApprovalManager(approval_gate=gate)
        request = manager.request("task-1", "wire transfer $10,000", RISK_HIGH)
        self.assertEqual(request.status, "denied")
        with self.assertRaises(ApprovalDeniedError):
            manager.require_granted(request.id)


class TestApprovalManagerPendingFlow(unittest.TestCase):
    def test_medium_risk_without_gate_stays_pending_until_granted(self):
        manager = ApprovalManager()
        request = manager.request("task-1", "post an update to Slack", RISK_MEDIUM)
        self.assertEqual(manager.check(request.id), "pending")

        manager.grant(request.id, reason="looks fine")

        self.assertEqual(manager.check(request.id), "granted")

    def test_deny_sets_status(self):
        manager = ApprovalManager()
        request = manager.request("task-1", "update project metadata", RISK_MEDIUM)
        manager.deny(request.id, reason="not now")
        self.assertEqual(manager.check(request.id), "denied")

    def test_expiration_is_computed_live_not_a_stored_flag(self):
        clock_value = [1000.0]
        manager = ApprovalManager(clock=lambda: clock_value[0], default_ttl_seconds=60.0)
        request = manager.request("task-1", "schedule a meeting", RISK_MEDIUM)

        self.assertEqual(manager.check(request.id), "pending")
        clock_value[0] += 61.0  # advance past expiration
        self.assertEqual(manager.check(request.id), "expired")

    def test_granting_after_expiration_raises(self):
        clock_value = [1000.0]
        manager = ApprovalManager(clock=lambda: clock_value[0], default_ttl_seconds=60.0)
        request = manager.request("task-1", "schedule a meeting", RISK_MEDIUM)
        clock_value[0] += 61.0

        with self.assertRaises(ApprovalExpiredError):
            manager.grant(request.id)

    def test_require_granted_raises_for_pending(self):
        manager = ApprovalManager()
        request = manager.request("task-1", "send a message", RISK_MEDIUM)
        with self.assertRaises(ApprovalDeniedError):
            manager.require_granted(request.id)


if __name__ == "__main__":
    unittest.main()
