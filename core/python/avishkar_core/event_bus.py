"""EventBus -- in-process, synchronous publish/subscribe.

See CONTRACT.md SS3 for the full contract, and schemas/event.schema.json
for the Event envelope shape.

Concurrency (Priority 17.4 platform-wide hardening pass, ADR-0024):
`_subscribers`/`_next_id` are guarded by a lock. This is a narrow,
additive exception to core/'s Phase 1 "locked" status -- justified
because the Phase 17 directive explicitly names EventBus as an audit/
harden target, and because the fix changes nothing about single-
threaded behavior (every existing core/ test still passes unmodified).
subscribe()/unsubscribe() mutate the dict/list; publish() takes a
consistent snapshot of matching handlers under the lock, then invokes
them *outside* it -- holding the lock during an arbitrary handler
would block every other publish()/subscribe()/unsubscribe() call for
as long as that handler runs, and a handler that itself calls back
into publish()/subscribe() (a realistic pattern -- see AuditLogger
subscribers) would deadlock on a non-reentrant lock.
"""

from __future__ import annotations

import dataclasses
import datetime
import threading
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
        self._lock = threading.Lock()

    def subscribe(self, event_type: str, handler: Callable[[Event], None]) -> Subscription:
        """event_type "*" subscribes to every event (for logging/audit use)."""
        with self._lock:
            self._next_id += 1
            subscription = Subscription(event_type=event_type, handler=handler, _id=self._next_id)
            self._subscribers.setdefault(event_type, []).append(subscription)
            return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        with self._lock:
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
        with self._lock:
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
