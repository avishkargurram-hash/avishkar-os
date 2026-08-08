"""Integration Policies -- access control, trust level, and sandboxing.
See CONTRACT.md SS4.

Human-in-the-loop approval reuses avishkar_agent.ApprovalGate directly
(ADR-0011 SS7) rather than a duplicate class -- see runtime.py for where
it's applied.
"""

from __future__ import annotations

import dataclasses
from typing import Optional, Tuple


@dataclasses.dataclass(frozen=True)
class AccessControlPolicy:
    allowed_callers: Optional[Tuple[str, ...]] = None  # None = allow all
    denied_callers: Tuple[str, ...] = ()

    def is_allowed(self, caller: Optional[str]) -> bool:
        if caller is not None and caller in self.denied_callers:
            return False
        if self.allowed_callers is None:
            return True
        return caller in self.allowed_callers


@dataclasses.dataclass(frozen=True)
class SecurityPolicy:
    """Trusted vs. untrusted tools, and the sandboxing requirement that
    goes with untrusted ones. See CONTRACT.md SS4 for why
    `require_sandbox=True` denies rather than pretends to sandbox in v1.
    """

    trust_level: str = "untrusted"  # "trusted" | "untrusted"
    require_sandbox: bool = False
    access_control: AccessControlPolicy = dataclasses.field(default_factory=AccessControlPolicy)

    def __post_init__(self) -> None:
        if self.trust_level not in ("trusted", "untrusted"):
            raise ValueError(f"SecurityPolicy.trust_level must be 'trusted' or 'untrusted', got {self.trust_level!r}")
