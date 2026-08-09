"""ApprovalManager. See CONTRACT.md SS4.

The actual gating mechanism is avishkar_agent.ApprovalGate, reused
directly (not reimplemented) -- the same precedent mcp-factory
established (ADR-0011 SS7). ApprovalManager adds the risk-tiering layer
(LOW auto-grants; MEDIUM/HIGH go through a gate, or stay pending for an
external grant()/deny() call when no gate is wired) that doesn't exist
anywhere else in this platform.
"""

from __future__ import annotations

import datetime
import time
from typing import Callable, Dict, Optional

from avishkar_agent import ApprovalGate, Task

from .errors import ApprovalDeniedError, ApprovalExpiredError
from .types import RISK_LOW, ApprovalRequest, new_id


def _iso(epoch_seconds: float) -> str:
    return datetime.datetime.fromtimestamp(epoch_seconds, tz=datetime.timezone.utc).isoformat()


class ApprovalManager:
    def __init__(
        self,
        *,
        approval_gate: Optional[ApprovalGate] = None,
        clock: Callable[[], float] = time.time,
        default_ttl_seconds: float = 3600.0,
    ) -> None:
        self._approval_gate = approval_gate
        self._clock = clock
        self._default_ttl_seconds = default_ttl_seconds
        self._requests: Dict[str, ApprovalRequest] = {}

    def request(self, task_id: str, action_description: str, risk_level: str) -> ApprovalRequest:
        now = self._clock()
        request_id = new_id("approval")

        if risk_level == RISK_LOW:
            record = ApprovalRequest(
                id=request_id, task_id=task_id, action_description=action_description,
                risk_level=risk_level, status="granted", auto=True,
                created_at=_iso(now), decided_at=_iso(now), reason="auto-granted: LOW risk",
            )
        elif self._approval_gate is not None:
            # Synchronous decision via the reused ApprovalGate -- see
            # module docstring.
            granted = self._approval_gate.evaluate(Task(input=action_description))
            record = ApprovalRequest(
                id=request_id, task_id=task_id, action_description=action_description,
                risk_level=risk_level, status="granted" if granted else "denied",
                created_at=_iso(now), decided_at=_iso(now),
                reason="ApprovalGate decision",
            )
        else:
            record = ApprovalRequest(
                id=request_id, task_id=task_id, action_description=action_description,
                risk_level=risk_level, status="pending",
                created_at=_iso(now), expiration=_iso(now + self._default_ttl_seconds),
            )

        self._requests[request_id] = record
        return record

    def grant(self, request_id: str, *, reason: str = "") -> ApprovalRequest:
        record = self._require(request_id)
        if self._is_expired(record):
            raise ApprovalExpiredError(f"approval request {request_id!r} expired before it was granted")
        record.status = "granted"
        record.decided_at = _iso(self._clock())
        record.reason = reason
        return record

    def deny(self, request_id: str, *, reason: str = "") -> ApprovalRequest:
        record = self._require(request_id)
        record.status = "denied"
        record.decided_at = _iso(self._clock())
        record.reason = reason
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
        try:
            return self._requests[request_id]
        except KeyError as exc:
            raise KeyError(f"no approval request with id {request_id!r}") from exc
