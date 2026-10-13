import unittest

from avishkar_layla.approval import ApprovalManager
from avishkar_layla.auth import AuthorizationManager
from avishkar_layla.errors import PermissionDeniedError, UnauthenticatedError
from avishkar_layla.identity import PERM_APPROVE, Principal
from avishkar_layla.types import RISK_HIGH


class TestApprovalManagerWithIdentity(unittest.TestCase):
    def _manager_and_sessions(self):
        auth = AuthorizationManager(clock=lambda: 0.0)
        requester = auth.issue_session(Principal(id="alice", kind="user"), ["operator"])
        approver = auth.issue_session(Principal(id="bob", kind="user"), ["admin"])
        manager = ApprovalManager(authorization=auth, clock=lambda: 0.0)
        return auth, manager, requester, approver

    def test_grant_requires_a_session_with_approve_permission(self):
        auth, manager, requester, approver = self._manager_and_sessions()
        request = manager.request("t1", "wire transfer $5000", RISK_HIGH, requested_by=requester.principal.id)

        granted = manager.grant(request.id, session_id=approver.id)

        self.assertEqual(granted.status, "granted")

    def test_grant_without_session_raises_when_authorization_wired(self):
        auth, manager, requester, approver = self._manager_and_sessions()
        request = manager.request("t1", "wire transfer $5000", RISK_HIGH, requested_by=requester.principal.id)

        with self.assertRaises(UnauthenticatedError):
            manager.grant(request.id, session_id=None)

    def test_grant_by_a_session_without_approve_permission_is_denied(self):
        auth, manager, requester, approver = self._manager_and_sessions()
        viewer = auth.issue_session(Principal(id="carol", kind="user"), ["viewer"])
        request = manager.request("t1", "wire transfer $5000", RISK_HIGH, requested_by=requester.principal.id)

        with self.assertRaises(PermissionDeniedError):
            manager.grant(request.id, session_id=viewer.id)

    def test_self_approval_is_always_denied(self):
        auth, manager, requester, approver = self._manager_and_sessions()
        # The requester is separately also an admin -- even so, they
        # can never approve their own request.
        requester_as_admin = auth.issue_session(Principal(id="alice", kind="user"), ["admin"])
        request = manager.request("t1", "wire transfer $5000", RISK_HIGH, requested_by="alice")

        with self.assertRaises(PermissionDeniedError) as ctx:
            manager.grant(request.id, session_id=requester_as_admin.id)
        self.assertIn("self-approval", str(ctx.exception))

    def test_without_authorization_wired_behavior_is_unchanged_from_phase_16(self):
        manager = ApprovalManager(clock=lambda: 0.0)  # no authorization= at all
        request = manager.request("t1", "wire transfer $5000", RISK_HIGH)
        granted = manager.grant(request.id)  # no session_id needed
        self.assertEqual(granted.status, "granted")

    def test_deny_also_requires_approve_permission(self):
        auth, manager, requester, approver = self._manager_and_sessions()
        request = manager.request("t1", "wire transfer $5000", RISK_HIGH, requested_by=requester.principal.id)
        denied = manager.deny(request.id, session_id=approver.id, reason="too risky")
        self.assertEqual(denied.status, "denied")


if __name__ == "__main__":
    unittest.main()
