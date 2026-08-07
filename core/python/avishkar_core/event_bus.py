"""EventBus -- in-process, synchronous publish/subscribe.

See CONTRACT.md SS3 for the full contract, and schemas/event.schema.json
for the Event envelope shape.
"""

from __future__ import annotations

import dataclasses
import datetime
import uuid
from typing import Callable, Dict, List

from .logging import get_logger

_logger = get_logger("core.event_bus")


@dataclasses.dataclass(frozen=True)
class Event:
    event_id: str
    event_type: str
    payload: dict
    timestamp: str
    source: str


@dataclasses.dataclass(frozen=True)
class Subscription:
    event_type: str
    handler: Callable[[Event], None]
    _id: int


class EventBus:
    """A single in-process event bus. Cross-process/distributed delivery
    is explicitly out of scope for v1 -- see core/README.md Future Roadmap.
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Subscription]] = {}
        self._next_id = 0

    def subscribe(self, event_type: str, handler: Callable[[Event], None]) -> Subscription:
        """event_type "*" subscribes to every event (for logging/audit use)."""
        self._next_id += 1
        subscription = Subscription(event_type=event_type, handler=handler, _id=self._next_id)
        self._subscribers.setdefault(event_type, []).append(subscription)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        bucket = self._subscribers.get(subscription.event_type, [])
        self._subscribers[subscription.event_type] = [
            s for s in bucket if s._id != subscription._id
        ]

    def publish(self, event_type: str, payload: dict, source: str) -> Event:
        """Construct and deliver an Event to every matching handler,
        synchronously, in subscription order. A handler that raises is
        caught, logged, and does not stop remaining handlers from running
        or propagate to the caller -- see CONTRACT.md SS3.
        """
        event = Event(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            payload=payload,
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            source=source,
        )
        handlers = list(self._subscribers.get(event_type, [])) + list(self._subscribers.get("*", []))
        for subscription in handlers:
            try:
                subscription.handler(event)
            except Exception as exc:  # noqa: BLE001 -- isolation is the point
                _logger.error(
                    f"EventBus handler for '{event_type}' raised",
                    exception=exc,
                    event_id=event.event_id,
                )
        return event
