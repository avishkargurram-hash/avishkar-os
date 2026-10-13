"""End-to-end Directive D Part VI chain: Sensor -> SensorMonitor ->
real EventBus -> EnvironmentalEventBuffer -> EnvironmentalChangeEvaluator
-> real ProactiveEngine.evaluate() -- proving every real piece this
pass built genuinely composes, exactly as CONTRACT.md SS38 describes.
Scheduler.schedule_recurring() drives SensorMonitor.check() (the "use
schedules... to wake intelligence only when required" mechanism);
nothing here calls handle_event() -- the trigger tops out at
ACTION_OBSERVE, recorded via AuditLogger, never an autonomous action.
"""

import unittest

from avishkar_agent import InMemoryMemoryPolicy
from avishkar_core import EventBus

from avishkar_layla import LaylaMemoryPolicy
from avishkar_layla.audit import AuditLogger
from avishkar_layla.environment.context import EnvironmentalChangeEvaluator, EnvironmentalEventBuffer
from avishkar_layla.environment.event_translation import SensorMonitor
from avishkar_layla.environment.sensors import Sensor, SensorReading
from avishkar_layla.notifications import NotificationManager
from avishkar_layla.proactive import ACTION_OBSERVE, ProactiveEngine
from avishkar_layla.scheduler import Scheduler
from avishkar_layla.session import SessionManager


class ScriptedConnectivitySensor(Sensor):
    """A deterministic fake standing in for NetworkConnectivitySensor
    -- everything downstream of it (SensorMonitor onward) is real.
    """

    sensor_type = "network_connectivity"

    def __init__(self, values):
        self.sensor_id = "network_connectivity"
        self._values = list(values)

    def read(self):
        return SensorReading(sensor_id=self.sensor_id, sensor_type=self.sensor_type, value=self._values.pop(0), unit="boolean")


class TestEnvironmentalAwarenessEndToEnd(unittest.TestCase):
    def test_full_chain_from_sensor_change_to_a_real_proactive_trigger(self):
        memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        sessions = SessionManager(memory)
        audit = AuditLogger(memory)
        notifications = NotificationManager()

        bus = EventBus()
        buffer = EnvironmentalEventBuffer(bus)
        evaluator = EnvironmentalChangeEvaluator(buffer)
        engine = ProactiveEngine(sessions, audit, notifications, extra_evaluators=(evaluator,))

        sensor = ScriptedConnectivitySensor([True, True, False])  # connectivity is lost on the 3rd check
        monitor = SensorMonitor(sensor, bus, source="test-environment")

        clock = {"t": 0.0}
        scheduler = Scheduler(clock=lambda: clock["t"])
        scheduler.schedule_recurring(10.0, monitor.check, start_at=0.0)

        # Tick 1 (t=0): first read, True -- publishes, but not a "lost" event.
        scheduler.tick(now=0.0)
        self.assertEqual(engine.evaluate(), ())

        # Tick 2 (t=10): still True -- no change, no publish.
        clock["t"] = 10.0
        scheduler.tick(now=10.0)
        self.assertEqual(engine.evaluate(), ())

        # Tick 3 (t=20): False -- a real change, publishes a real
        # EventBus event, which the buffer captures and the evaluator
        # turns into a real ProactiveTrigger.
        clock["t"] = 20.0
        scheduler.tick(now=20.0)
        triggers = engine.evaluate()

        self.assertEqual(len(triggers), 1)
        self.assertEqual(triggers[0].action_level, ACTION_OBSERVE)
        self.assertIn("Network connectivity was lost", triggers[0].description)

        # Re-evaluating again must not re-surface the same event.
        self.assertEqual(engine.evaluate(), ())


if __name__ == "__main__":
    unittest.main()
