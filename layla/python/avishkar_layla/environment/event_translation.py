"""SensorMonitor -- translates real sensor readings into real
`avishkar_core.EventBus` events, ONLY on a genuine state change or
threshold crossing. See CONTRACT.md SS38.

This is the concrete answer to Directive D Part VI's "do NOT poll an
LLM continuously. Use events, schedules, thresholds and state changes
to wake Layla intelligence only when required": `.check()` is cheap,
non-LLM Python (one sensor read + one comparison against the last
reading), meant to be invoked from a real `Scheduler.schedule_recurring()`
job (already exists -- not a new polling mechanism) -- and it only
calls `EventBus.publish()` when something genuinely changed, so a
quiet environment produces zero events, not a periodic no-op flood.
"""

from __future__ import annotations

from typing import Any, Optional

from avishkar_core import EventBus

from .sensors import Sensor, SensorReading

ENVIRONMENT_EVENT_PREFIX = "layla.environment."


def _is_numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class SensorMonitor:
    def __init__(
        self, sensor: Sensor, event_bus: EventBus, *, source: str = "environment", min_change: Optional[float] = None,
    ) -> None:
        self._sensor = sensor
        self._event_bus = event_bus
        self._source = source
        self._min_change = min_change
        self._last_reading: Optional[SensorReading] = None

    @property
    def event_type(self) -> str:
        return f"{ENVIRONMENT_EVENT_PREFIX}{self._sensor.sensor_type}"

    def _changed(self, new: SensorReading) -> bool:
        if self._last_reading is None:
            return True
        old_value, new_value = self._last_reading.value, new.value
        if _is_numeric(old_value) and _is_numeric(new_value):
            if self._min_change is None:
                return old_value != new_value
            return abs(new_value - old_value) >= self._min_change
        return old_value != new_value

    def check(self):
        """Reads the real sensor once. Returns the real `Event` if a
        genuine change/threshold crossing published one, else `None`
        (the common case -- most checks publish nothing).
        """
        reading = self._sensor.read()
        if not self._changed(reading):
            self._last_reading = reading
            return None

        previous_value = self._last_reading.value if self._last_reading is not None else None
        self._last_reading = reading
        return self._event_bus.publish(
            self.event_type,
            {
                "sensor_id": reading.sensor_id, "value": reading.value, "unit": reading.unit,
                "previous_value": previous_value, "confidence": reading.confidence, "metadata": dict(reading.metadata),
            },
            self._source,
        )
