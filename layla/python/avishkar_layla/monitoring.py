"""HealthMonitor -- classifies real signals into Notifications (or
None, when nothing is worth surfacing). See CONTRACT.md SS8. Never
fabricates a signal: every method here takes a real DelegationRecord/
ApprovalRequest this platform already produced.
"""

from __future__ import annotations

from typing import Optional

from .notifications import NotificationManager
from .types import (
    SEVERITY_ACTION_REQUIRED,
    SEVERITY_WARNING,
    ApprovalRequest,
    DelegationRecord,
    Notification,
)


class HealthMonitor:
    def __init__(self, notification_manager: NotificationManager) -> None:
        self._notifications = notification_manager

    def observe_delegation(self, record: DelegationRecord) -> Optional[Notification]:
        if record.status == "failed":
            return self._notifications.notify(
                SEVERITY_WARNING,
                f"Delegation of step '{record.step_id}' to '{record.agent_name or '(unresolved)'}' failed: {record.error}",
                source="delegation",
            )
        if record.status == "timeout":
            return self._notifications.notify(
                SEVERITY_ACTION_REQUIRED,
                f"Delegation of step '{record.step_id}' timed out after {record.attempts} attempt(s)",
                source="delegation",
            )
        if record.status == "denied":
            return self._notifications.notify(
                SEVERITY_ACTION_REQUIRED,
                f"Delegation of step '{record.step_id}' was denied approval",
                source="approval",
            )
        return None  # "completed"/"pending" -- nothing worth surfacing

    def observe_approval_expired(self, request: ApprovalRequest) -> Optional[Notification]:
        if request.status != "pending":
            return None
        return self._notifications.notify(
            SEVERITY_ACTION_REQUIRED,
            f"Approval request '{request.id}' expired unresolved: {request.action_description}",
            source="approval",
        )
