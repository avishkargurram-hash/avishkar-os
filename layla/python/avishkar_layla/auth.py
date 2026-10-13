"""AuthorizationManager -- authentication (who is this session) and
authorization (may this session do that) for Layla. See CONTRACT.md
SS15, DECISIONS.md ADR-0021.

Additive to every existing Layla component: ExecutiveRuntime/
ApprovalManager/DelegationEngine all accept this as an *optional*
constructor argument. When omitted, behavior is unchanged from Phase
16 (no identity enforcement) -- every one of Phase 16's 119 tests
keeps passing unmodified. When supplied, every entry point requires a
valid Session and the risk-appropriate permission before proceeding.
"""

from __future__ import annotations

import datetime
import time
from typing import Callable, Dict, FrozenSet, Mapping, Optional, Sequence

from .errors import EscalationDeniedError, PermissionDeniedError, UnauthenticatedError
from .identity import (
    AGENT_FORBIDDEN_PERMISSIONS,
    BUILTIN_ROLES,
    Principal,
    Role,
    Session,
)
from .types import new_id


def _iso(epoch_seconds: float) -> str:
    return datetime.datetime.fromtimestamp(epoch_seconds, tz=datetime.timezone.utc).isoformat()


class AuthorizationManager:
    def __init__(self, *, roles: Mapping[str, Role] = BUILTIN_ROLES, clock: Callable[[], float] = time.time) -> None:
        self._roles: Dict[str, Role] = dict(roles)
        self._sessions: Dict[str, Session] = {}
        self._clock = clock

    def register_role(self, role: Role) -> None:
        """Extends the built-in role set -- the seam a real deployment
        adds its own roles through, without editing this framework.
        """
        self._roles[role.name] = role

    def issue_session(
        self, principal: Principal, role_names: Sequence[str], *, ttl_seconds: Optional[float] = None
    ) -> Session:
        for name in role_names:
            role = self._require_role(name)
            self._check_no_escalation(principal, role)
        now = self._clock()
        session = Session(
            id=new_id("session"), principal=principal, role_names=tuple(role_names),
            issued_at=_iso(now), expires_at=_iso(now + ttl_seconds) if ttl_seconds is not None else None,
        )
        self._sessions[session.id] = session
        return session

    def revoke_session(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session is not None:
            session.revoked = True

    def authenticate(self, session_id: str) -> Session:
        session = self._sessions.get(session_id)
        if session is None:
            raise UnauthenticatedError(f"no such session {session_id!r}")
        if session.revoked:
            raise UnauthenticatedError(f"session {session_id!r} was revoked")
        if session.expires_at is not None:
            if self._clock() > datetime.datetime.fromisoformat(session.expires_at).timestamp():
                raise UnauthenticatedError(f"session {session_id!r} expired at {session.expires_at}")
        return session

    def permissions_for(self, session: Session) -> FrozenSet[str]:
        perms = set()
        for name in session.role_names:
            perms |= set(self._roles[name].permissions)
        return frozenset(perms)

    def allowed_capabilities_for(self, session: Session) -> Optional[FrozenSet[str]]:
        """None means "no capability-level restriction" (every role
        granted has allowed_capabilities=None). If ANY granted role
        restricts capabilities, the effective set is the union of all
        roles' restrictions -- least privilege composes by union of
        what's explicitly granted, not by accident of role ordering.
        """
        restrictions = [
            self._roles[name].allowed_capabilities
            for name in session.role_names
            if self._roles[name].allowed_capabilities is not None
        ]
        if not restrictions:
            return None
        allowed: set = set()
        for r in restrictions:
            allowed |= set(r)
        return frozenset(allowed)

    def authorize(self, session: Session, permission: str) -> None:
        if permission not in self.permissions_for(session):
            raise PermissionDeniedError(
                f"principal {session.principal.id!r} (session {session.id!r}) lacks permission {permission!r}"
            )

    def authorize_capability(self, session: Session, capability: str) -> None:
        allowed = self.allowed_capabilities_for(session)
        if allowed is not None and capability not in allowed:
            raise PermissionDeniedError(
                f"principal {session.principal.id!r} (session {session.id!r}) is not permitted to "
                f"invoke capability {capability!r} (allowed: {sorted(allowed)})"
            )

    def require(self, session_id: str, permission: str) -> Session:
        session = self.authenticate(session_id)
        self.authorize(session, permission)
        return session

    def _require_role(self, name: str) -> Role:
        try:
            return self._roles[name]
        except KeyError as exc:
            raise KeyError(f"no such role {name!r} -- register it first via register_role()") from exc

    def _check_no_escalation(self, principal: Principal, role: Role) -> None:
        if principal.kind == "agent" and (set(role.permissions) & AGENT_FORBIDDEN_PERMISSIONS):
            raise EscalationDeniedError(
                f"principal {principal.id!r} is kind='agent' and cannot be granted role {role.name!r} "
                f"(would include {sorted(set(role.permissions) & AGENT_FORBIDDEN_PERMISSIONS)}) -- "
                f"an agent can never hold high-risk or approval authority, structurally, not by convention"
            )
