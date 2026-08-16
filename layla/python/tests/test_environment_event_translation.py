"""SensorMonitor tests -- uses a real avishkar_core.EventBus (not a
fake) with a deterministic fake Sensor, so the threshold/change-
detection logic and the real publish() call are both genuinely
exercised.
"""

import unittest

from avishkar_core import EventBus

from avishkar_layla.environment.event_translation import ENVIRONMENT_EVENT_PREFIX, SensorMonitor
from avishkar_layla.environment.sensors import Sensor, SensorReading


class FakeSensor(Sensor):
    sensor_type = "fake"

    def __init__(self, values, *, sensor_id="fake-1"):
        self.sensor_id = sensor_id
        self._values = list(values)

    def read(self):
        value = self._values.pop(0)
        return SensorReading(sensor_id=self.sensor_id, sensor_type=self.sensor_type, value=value, unit="unit")


class TestSensorMonitor(unittest.TestCase):
    def test_first_read_always_publishes(self):
        bus = EventBus()
        published = []
        bus.subscribe(f"{ENVIRONMENT_EVENT_PREFIX}fake", lambda e: published.append(e))
        monitor = SensorMonitor(FakeSensor([10]), bus, source="test")

        event = monitor.check()

        self.assertIsNotNone(event)
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0].payload["value"], 10)
        self.assertIsNone(published[0].payload["previous_value"])

    def test_unchanged_value_does_not_publish(self):
        bus = EventBus()
        published = []
        bus.subscribe(f"{ENVIRONMENT_EVENT_PREFIX}fake", lambda e: published.append(e))
        monitor = SensorMonitor(FakeSensor([10, 10, 10]), bus, source="test")

        monitor.check()
        monitor.check()
        monitor.check()

        self.assertEqual(len(published), 1)  # only the first (always-publishes) read

    def test_changed_value_publishes_with_real_previous_value(self):
        bus = EventBus()
        published = []
        bus.subscribe(f"{ENVIRONMENT_EVENT_PREFIX}fake", lambda e: published.append(e))
        monitor = SensorMonitor(FakeSensor([10, 20]), bus, source="test")

        monitor.check()
        event = monitor.check()

        self.assertEqual(event.payload["value"], 20)
        self.assertEqual(event.payload["previous_value"], 10)
        self.assertEqual(len(published), 2)

    def test_min_change_threshold_suppresses_small_fluctuations(self):
        bus = EventBus()
        published = []
        bus.subscribe(f"{ENVIRONMENT_EVENT_PREFIX}fake", lambda e: published.append(e))
        monitor = SensorMonitor(FakeSensor([50.0, 50.5, 60.0]), bus, source="test", min_change=5.0)

        monitor.check()  # first read: publishes
        monitor.check()  # 50.0 -> 50.5: below threshold, no publish
        monitor.check()  # 50.5 -> 60.0: crosses threshold, publishes

        self.assertEqual(len(published), 2)
        self.assertEqual(published[-1].payload["value"], 60.0)

    def test_event_type_is_prefixed_by_sensor_type(self):
        bus = EventBus()
        monitor = SensorMonitor(FakeSensor([1]), bus, source="test")
        self.assertEqual(monitor.event_type, f"{ENVIRONMENT_EVENT_PREFIX}fake")

    def test_boolean_value_change_always_publishes_regardless_of_min_change(self):
        bus = EventBus()
        published = []
        bus.subscribe(f"{ENVIRONMENT_EVENT_PREFIX}fake", lambda e: published.append(e))
        monitor = SensorMonitor(FakeSensor([True, False]), bus, source="test", min_change=100.0)

        monitor.check()
        event = monitor.check()

        self.assertIsNotNone(event)
        self.assertEqual(len(published), 2)


if __name__ == "__main__":
    unittest.main()
