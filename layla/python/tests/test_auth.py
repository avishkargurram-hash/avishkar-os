import unittest

from avishkar_layla.auth import AuthorizationManager
from avishkar_layla.errors import EscalationDeniedError, PermissionDeniedError, UnauthenticatedError
from avishkar_layla.identity import (
    PERM_APPROVE,
    PERM_COMMAND,
    PERM_INVOKE_AGENT,
    PERM_INVOKE_AGENT_HIGH_RISK,
    PERM_INVOKE_AGENT_WRITE,
    Principal,
    Role,
)


class TestSessionIssuanceAndAuthentication(unittest.TestCase):
    def test_issue_and_authenticate_a_session(self):
        manager = AuthorizationManager(clock=lambda: 0.0)
        user = Principal(id="alice", kind="user")
        session = manager.issue_session(user, ["operator"])

        authenticated = manager.authenticate(session.id)

        self.assertEqual(authenticated.principal.id, "alice")

    def test_unknown_session_id_raises(self):
        manager = AuthorizationManager(clock=lambda: 0.0)
        with self.assertRaises(UnauthenticatedError):
            manager.authenticate("does-not-exist")

    def test_revoked_session_cannot_authenticate(self):
        manager = AuthorizationManager(clock=lambda: 0.0)
        user = Principal(id="alice", kind="user")
        session = manager.issue_session(user, ["viewer"])

        manager.revoke_session(session.id)

        with self.assertRaises(UnauthenticatedError):
            manager.authenticate(session.id)

    def test_expired_session_cannot_authenticate(self):
        clock = [1000.0]
        manager = AuthorizationManager(clock=lambda: clock[0])
        user = Principal(id="alice", kind="user")
        session = manager.issue_session(user, ["viewer"], ttl_seconds=60.0)

        clock[0] += 61.0

        with self.assertRaises(UnauthenticatedError):
            manager.authenticate(session.id)

    def test_session_without_ttl_never_expires(self):
        clock = [0.0]
        manager = AuthorizationManager(clock=lambda: clock[0])
        session = manager.issue_session(Principal(id="alice", kind="user"), ["viewer"])
        clock[0] += 10_000_000.0
        manager.authenticate(session.id)  # must not raise


class TestPermissions(unittest.TestCase):
    def test_viewer_can_command_and_invoke_low_risk_only(self):
        manager = AuthorizationManager(clock=lambda: 0.0)
        session = manager.issue_session(Principal(id="alice", kind="user"), ["viewer"])

        manager.authorize(session, PERM_COMMAND)
        manager.authorize(session, PERM_INVOKE_AGENT)
        with self.assertRaises(PermissionDeniedError):
            manager.authorize(session, PERM_INVOKE_AGENT_HIGH_RISK)

    def test_admin_has_approval_authority(self):
        manager = AuthorizationManager(clock=lambda: 0.0)
        session = manager.issue_session(Principal(id="alice", kind="user"), ["admin"])
        manager.authorize(session, PERM_APPROVE)

    def test_require_combines_authenticate_and_authorize(self):
        manager = AuthorizationManager(clock=lambda: 0.0)
        session = manager.issue_session(Principal(id="alice", kind="user"), ["viewer"])

        manager.require(session.id, PERM_COMMAND)
        with self.assertRaises(PermissionDeniedError):
            manager.require(session.id, PERM_APPROVE)

    def test_custom_role_can_be_registered(self):
        manager = AuthorizationManager(clock=lambda: 0.0)
        manager.register_role(Role("researcher", (PERM_COMMAND, PERM_INVOKE_AGENT)))
        session = manager.issue_session(Principal(id="bot", kind="user"), ["researcher"])
        manager.authorize(session, PERM_INVOKE_AGENT)


class TestCapabilityRestriction(unittest.TestCase):
    def test_no_restriction_by_default(self):
        manager = AuthorizationManager(clock=lambda: 0.0)
        session = manager.issue_session(Principal(id="alice", kind="user"), ["operator"])
        self.assertIsNone(manager.allowed_capabilities_for(session))
        manager.authorize_capability(session, "anything-at-all")  # must not raise

    def test_role_scoped_to_specific_capabilities(self):
        manager = AuthorizationManager(clock=lambda: 0.0)
        manager.register_role(Role("finance-only", (PERM_COMMAND, PERM_INVOKE_AGENT), allowed_capabilities=("finance-economics",)))
        session = manager.issue_session(Principal(id="alice", kind="user"), ["finance-only"])

        manager.authorize_capability(session, "finance-economics")
        with self.assertRaises(PermissionDeniedError):
            manager.authorize_capability(session, "legal-compliance")


class TestAgentSelfEscalationPrevention(unittest.TestCase):
    def test_agent_principal_cannot_be_issued_the_admin_role(self):
        manager = AuthorizationManager(clock=lambda: 0.0)
        agent = Principal(id="research-intelligence", kind="agent")
        with self.assertRaises(EscalationDeniedError):
            manager.issue_session(agent, ["admin"])

    def test_agent_principal_cannot_be_issued_a_custom_role_with_approval_authority(self):
        manager = AuthorizationManager(clock=lambda: 0.0)
        manager.register_role(Role("sneaky", (PERM_COMMAND, PERM_APPROVE)))
        agent = Principal(id="some-agent", kind="agent")
        with self.assertRaises(EscalationDeniedError):
            manager.issue_session(agent, ["sneaky"])

    def test_agent_principal_can_be_issued_the_builtin_agent_role(self):
        manager = AuthorizationManager(clock=lambda: 0.0)
        agent = Principal(id="research-intelligence", kind="agent")
        session = manager.issue_session(agent, ["agent"])  # must not raise
        manager.authorize(session, PERM_INVOKE_AGENT_WRITE)
        with self.assertRaises(PermissionDeniedError):
            manager.authorize(session, PERM_INVOKE_AGENT_HIGH_RISK)

    def test_user_principal_can_be_issued_admin_without_restriction(self):
        manager = AuthorizationManager(clock=lambda: 0.0)
        user = Principal(id="alice", kind="user")
        manager.issue_session(user, ["admin"])  # must not raise


if __name__ == "__main__":
    unittest.main()
