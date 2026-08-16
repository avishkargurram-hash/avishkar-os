"""EnvironmentalEventBuffer / EnvironmentalChangeEvaluator -- the
"Perception/Context" step of Directive D Part VI's Sensor -> Event ->
EventBus -> Perception/Context -> Layla -> Decision chain. See
CONTRACT.md SS38.

`EventBus.subscribe()` only matches an exact `event_type` or the
literal wildcard `"*"` (core/'s locked implementation -- no prefix
wildcards); `EnvironmentalEventBuffer` subscribes to `"*"` and filters
by the `layla.environment.` prefix itself, rather than asking core/ to
grow prefix-matching it doesn't have (§0: core/ stays authoritative
and unmodified).

`EnvironmentalChangeEvaluator` is a real `proactive.TriggerEvaluator`
(ADR-0026) a deployment can pass into `ProactiveEngine(extra_evaluators=(...))`
-- capped at `ACTION_OBSERVE`, same discipline as every other built-in
evaluator (a lost network connection is a reason to look, not
sufficient evidence for `ExecutiveRuntime.handle_event()` to run
autonomously). It never calls `handle_event()` itself.
"""

from __future__ import annotations

from collections import deque
from typing import Deque, Optional, Sequence, Set, Tuple

from avishkar_core import Event, EventBus

from ..proactive import ACTION_OBSERVE, ProactiveEngine, ProactiveTrigger
from .event_translation import ENVIRONMENT_EVENT_PREFIX


class EnvironmentalEventBuffer:
    def __init__(self, event_bus: EventBus, *, max_events: int = 50) -> None:
        self._events: Deque[Event] = deque(maxlen=max_events)
        event_bus.subscribe("*", self._on_event)

    def _on_event(self, event: Event) -> None:
        if event.event_type.startswith(ENVIRONMENT_EVENT_PREFIX):
            self._events.append(event)

    def recent(self, *, event_type: Optional[str] = None) -> Tuple[Event, ...]:
        if event_type is None:
            return tuple(self._events)
        return tuple(e for e in self._events if e.event_type == event_type)


class EnvironmentalChangeEvaluator:
    """A stateful, real `TriggerEvaluator`: emits one `ACTION_OBSERVE`
    trigger per genuinely new "network connectivity lost" event found
    in the buffer -- tracks which event ids it has already surfaced
    (`_seen`) so a still-buffered event isn't re-triggered on every
    `ProactiveEngine.evaluate()` tick (the exact "retry storm" class
    Directive D Part XII warns against).
    """

    def __init__(self, buffer: EnvironmentalEventBuffer) -> None:
        self._buffer = buffer
        self._seen: Set[str] = set()

    def __call__(self, engine: ProactiveEngine) -> Sequence[ProactiveTrigger]:
        triggers = []
        for event in self._buffer.recent(event_type=f"{ENVIRONMENT_EVENT_PREFIX}network_connectivity"):
            if event.event_id in self._seen:
                continue
            self._seen.add(event.event_id)
            if event.payload.get("value") is False:
                triggers.append(
                    ProactiveTrigger(
                        id=f"env-net-{event.event_id}", action_level=ACTION_OBSERVE,
                        description="Network connectivity was lost.",
                        evidence={"event_id": event.event_id, "payload": event.payload}, source="environmental_change",
                    )
                )
        return triggers
