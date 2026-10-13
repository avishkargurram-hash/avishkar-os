"""NotificationManager. See CONTRACT.md SS8."""

from __future__ import annotations

import datetime
from typing import List, Optional, Tuple

from .types import SEVERITY_ORDER, Notification


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class NotificationManager:
    def __init__(self) -> None:
        self._notifications: List[Notification] = []

    def notify(self, severity: str, message: str, source: str) -> Notification:
        notification = Notification(severity=severity, message=message, source=source, created_at=_now())
        self._notifications.append(notification)
        return notification

    def pending(self, min_severity: Optional[str] = None) -> Tuple[Notification, ...]:
        if min_severity is None:
            return tuple(self._notifications)
        threshold = SEVERITY_ORDER.index(min_severity)
        return tuple(n for n in self._notifications if SEVERITY_ORDER.index(n.severity) >= threshold)

    def clear(self) -> None:
        self._notifications = []
