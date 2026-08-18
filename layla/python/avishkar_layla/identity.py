"""Identity primitives for Layla. See CONTRACT.md SS15 (Priority 17.1,
ADR-0021).

Deliberately minimal: Principal/Session/Role/Permission are plain data,
no OAuth/OIDC/JWT machinery. Built as a clean extensible seam a real
identity provider integrates behind later (see README.md Priority
17.1 Future Roadmap) -- not invented enterprise infrastructure this
platform doesn't need yet.
"""

from __future__ import annotations

import dataclasses
from typing import Optional, Tuple

# --- Permission vocabulary ---------------------------------------------
# A fixed, small set -- not an open-ended RBAC string namespace. Adding a
# new permission is a deliberate code change (this list), not a runtime
# string a caller can invent to bypass enforcement.

PERM_COMMAND = "layla.command"  # may submit a request to Layla at all
PERM_INVOKE_AGENT = "agent.invoke"  # may have Layla delegate a LOW-risk step
PERM_INVOKE_AGENT_WRITE = "agent.invoke.write"  # MEDIUM-risk step
PERM_INVOKE_AGENT_HIGH_RISK = "agent.invoke.high_risk"  # HIGH-risk step
PERM_APPROVE = "approval.decide"  # may grant/deny a pending ApprovalRequest
PERM_TOOL_INVOKE = "tool.invoke"  # reserved: direct tool/MCP invocation seam

ALL_PERMISSIONS = frozenset({
    PERM_COMMAND, PERM_INVOKE_AGENT, PERM_INVOKE_AGENT_WRITE,
    PERM_INVOKE_AGENT_HIGH_RISK, PERM_APPROVE, PERM_TOOL_INVOKE,
})

# Maps risk.classify_risk()'s output to the permission required to
# trigger an action at that tier -- the identity/risk integration point
# ADR-0021 calls for.
RISK_PERMISSION = {
    "LOW": PERM_INVOKE_AGENT,
    "MEDIUM": PERM_INVOKE_AGENT_WRITE,
    "HIGH": PERM_INVOKE_AGENT_HIGH_RISK,
}

# Permissions an "agent" kind Principal (see below) can never hold --
# the structural anti-escalation ceiling (Priority 17.1 SS5). Enforced
# in AuthorizationManager.issue_session/grant_role, not just by
# convention in the built-in roles below.
AGENT_FORBIDDEN_PERMISSIONS = frozenset({PERM_INVOKE_AGENT_HIGH_RISK, PERM_APPROVE})


@dataclasses.dataclass(frozen=True)
class Principal:
    """Who is acting: a human user, a Chief Domain Agent acting on its
    own (e.g. from a scheduled job), or the system itself.
    """

    id: str
    kind: str  # "user" | "agent" | "system"
    display_name: str = ""


@dataclasses.dataclass(frozen=True)
class Role:
    """A named bundle of permissions, optionally further restricted to
    a specific set of capabilities (agent names) -- the least-privilege
    capability enforcement seam (Priority 17.1 SS4). `None` means "no
    capability-level restriction beyond the risk-tier permissions."
    """

    name: str
    permissions: Tuple[str, ...]
    allowed_capabilities: Optional[Tuple[str, ...]] = None


@dataclasses.dataclass
class Session:
    id: str
    principal: Principal
    role_names: Tuple[str, ...]
    issued_at: str
    expires_at: Optional[str] = None
    revoked: bool = False


# --- Built-in roles ------------------------------------------------------
# A real, minimal starter set -- not exhaustive. A deployment registers
# its own via AuthorizationManager.register_role().

ROLE_VIEWER = Role("viewer", (PERM_COMMAND, PERM_INVOKE_AGENT))
ROLE_OPERATOR = Role("operator", (PERM_COMMAND, PERM_INVOKE_AGENT, PERM_INVOKE_AGENT_WRITE))
ROLE_ADMIN = Role(
    "admin",
    (PERM_COMMAND, PERM_INVOKE_AGENT, PERM_INVOKE_AGENT_WRITE, PERM_INVOKE_AGENT_HIGH_RISK, PERM_APPROVE),
)
# Deliberately excludes PERM_INVOKE_AGENT_HIGH_RISK and PERM_APPROVE --
# an autonomous agent-kind Principal can request LOW/MEDIUM-risk work
# but can never trigger a HIGH-risk action or approve its own (or any)
# pending request. This is belt (this role) AND suspenders (the
# structural AuthorizationManager check) -- see AGENT_FORBIDDEN_PERMISSIONS.
ROLE_AGENT = Role("agent", (PERM_COMMAND, PERM_INVOKE_AGENT, PERM_INVOKE_AGENT_WRITE))

BUILTIN_ROLES = {r.name: r for r in (ROLE_VIEWER, ROLE_OPERATOR, ROLE_ADMIN, ROLE_AGENT)}
