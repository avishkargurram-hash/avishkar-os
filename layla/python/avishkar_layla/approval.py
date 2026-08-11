"""ApprovalManager. See CONTRACT.md SS4.

The actual gating mechanism is avishkar_agent.ApprovalGate, reused
directly (not reimplemented) -- the same precedent mcp-factory
established (ADR-0011 SS7). ApprovalManager adds the risk-tiering layer
(LOW auto-grants; MEDIUM/HIGH go through a gate, or stay pending for an
external grant()/deny() call when no gate is wired) that doesn't exist
anywhere else in this platform.

Identity (Priority 17.1, ADR-0021): `authorization` is an *optional*
constructor argument. When omitted, grant()/deny() behave exactly as
in Phase 16 -- no identity enforcement, every existing test unaffected.
When supplied, grant()/deny() require a valid `session_id` holding
PERM_APPROVE, and refuse self-approval (the same principal that
requested an action can never be the one who approves it).

Durability (Priority 17.3, ADR-0023): `memory` is an *optional*
constructor argument. When omitted, `ApprovalRequest`s live only in an
in-process dict, exactly as in Phase 16/17.1 -- lost on restart, same
as before. When supplied (as `ExecutiveRuntime` always does, since it
already requires a `memory`), every request/grant/deny is also
persisted through the same `LaylaMemoryPolicy` every other Layla
component uses (`kind="long_term"`, `approval:{request_id}`) -- a
pending approval, or the outcome of one that was decided while this
process was down, survives a restart. See CONTRACT.md SS17.
"""

from __future__ import annotations

import dataclasses
import datetime
import time
from typing import Any, Callable, Dict, Optional

from avishkar_agent import ApprovalGate, Task

from .errors import ApprovalDeniedError, ApprovalExpiredError, PermissionDeniedError
from .identity import PERM_APPROVE
from .memory_policy import LaylaMemoryPolicy
from .types import RISK_LOW, ApprovalRequest, new_id

_KIND = "long_term"


def _iso(epoch_seconds: float) -> str:
    return datetime.datetime.fromtimestamp(epoch_seconds, tz=datetime.timezone.utc).isoformat()


class ApprovalManager:
    def __init__(
        self,
        *,
        approval_gate: Optional[ApprovalGate] = None,
        authorization: Optional[Any] = None,
        memory: Optional[LaylaMemoryPolicy] = None,
        clock: Callable[[], float] = time.time,
        default_ttl_seconds: float = 3600.0,
    ) -> None:
        self._approval_gate = approval_gate
        self._authorization = authorization
        self._memory = memory
        self._clock = clock
        self._default_ttl_seconds = default_ttl_seconds
        self._requests: Dict[str, ApprovalRequest] = {}

    def _save(self, record: ApprovalRequest) -> None:
        self._requests[record.id] = record
        if self._memory is not None:
            self._memory.remember(
                _KIND, f"approval:{record.id}", dataclasses.asdict(record),
                provenance="approval-manager", importance="high",
            )

    def request(
        self, task_id: str, action_description: str, risk_level: str, *, requested_by: Optional[str] = None
    ) -> ApprovalRequest:
        now = self._clock()
        request_id = new_id("approval")

        if risk_level == RISK_LOW:
            record = ApprovalRequest(
                id=request_id, task_id=task_id, action_description=action_description,
                risk_level=risk_level, status="granted", auto=True,
                created_at=_iso(now), decided_at=_iso(now), reason="auto-granted: LOW risk",
                requested_by=requested_by,
            )
        elif self._approval_gate is not None:
            # Synchronous decision via the reused ApprovalGate -- see
            # module docstring.
            granted = self._approval_gate.evaluate(Task(input=action_description))
            record = ApprovalRequest(
                id=request_id, task_id=task_id, action_description=action_description,
                risk_level=risk_level, status="granted" if granted else "denied",
                created_at=_iso(now), decided_at=_iso(now),
                reason="ApprovalGate decision", requested_by=requested_by,
            )
        else:
            record = ApprovalRequest(
                id=request_id, task_id=task_id, action_description=action_description,
                risk_level=risk_level, status="pending",
                created_at=_iso(now), expiration=_iso(now + self._default_ttl_seconds),
                requested_by=requested_by,
            )

        self._save(record)
        return record

    def grant(self, request_id: str, *, session_id: Optional[str] = None, reason: str = "") -> ApprovalRequest:
        record = self._require(request_id)
        if self._is_expired(record):
            raise ApprovalExpiredError(f"approval request {request_id!r} expired before it was granted")
        if self._authorization is not None:
            session = self._authorization.require(session_id, PERM_APPROVE)
            if record.requested_by is not None and session.principal.id == record.requested_by:
                raise PermissionDeniedError(
                    f"principal {session.principal.id!r} cannot approve its own request {request_id!r} "
                    f"(self-approval is never allowed)"
                )
        record.status = "granted"
        record.decided_at = _iso(self._clock())
        record.reason = reason
        self._save(record)
        return record

    def deny(self, request_id: str, *, session_id: Optional[str] = None, reason: str = "") -> ApprovalRequest:
        record = self._require(request_id)
        if self._authorization is not None:
            self._authorization.require(session_id, PERM_APPROVE)
        record.status = "denied"
        record.decided_at = _iso(self._clock())
        record.reason = reason
        self._save(record)
        return record

    def check(self, request_id: str) -> str:
        """Returns 'pending' | 'granted' | 'denied' | 'expired' -- expiry
        is always computed live from `expiration`, never a stored flag
        that could drift (CONTRACT.md SS4).
        """
        record = self._require(request_id)
        if record.status == "pending" and self._is_expired(record):
            return "expired"
        return record.status

    def require_granted(self, request_id: str) -> None:
        status = self.check(request_id)
        if status == "expired":
            raise ApprovalExpiredError(f"approval request {request_id!r} has expired")
        if status == "denied":
            raise ApprovalDeniedError(f"approval request {request_id!r} was denied")
        if status != "granted":
            raise ApprovalDeniedError(f"approval request {request_id!r} is not granted (status={status!r})")

    def _is_expired(self, record: ApprovalRequest) -> bool:
        if record.expiration is None:
            return False
        return self._clock() > datetime.datetime.fromisoformat(record.expiration).timestamp()

    def _require(self, request_id: str) -> ApprovalRequest:
        record = self._requests.get(request_id)
        if record is not None:
            return record
        if self._memory is not None:
            stored = self._memory.recall(_KIND, f"approval:{request_id}")
            if stored is not None:
                record = ApprovalRequest(**stored.value)
                self._requests[request_id] = record  # cache for subsequent calls this process
                return record
        raise KeyError(f"no approval request with id {request_id!r}")
