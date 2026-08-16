"""EnvironmentalEventBuffer / EnvironmentalChangeEvaluator tests --
real avishkar_core.EventBus throughout. Confirms the buffer correctly
filters non-environment events (EventBus's real "*" wildcard has no
prefix matching, so filtering is this module's own job), and that the
evaluator never re-emits a trigger for an event it already surfaced
(the real "retry storm" prevention Directive D Part XII asks for).
"""

import unittest

from avishkar_core import EventBus

from avishkar_layla.environment.context import EnvironmentalChangeEvaluator, EnvironmentalEventBuffer
from avishkar_layla.proactive import ACTION_OBSERVE


class TestEnvironmentalEventBuffer(unittest.TestCase):
    def test_only_environment_prefixed_events_are_kept(self):
        bus = EventBus()
        buffer = EnvironmentalEventBuffer(bus)

        bus.publish("layla.environment.battery", {"value": 50}, "test")
        bus.publish("layla.delegation.completed", {"x": 1}, "test")  # NOT environment-prefixed
        bus.publish("layla.environment.system_load", {"value": 80}, "test")

        recent = buffer.recent()
        self.assertEqual(len(recent), 2)
        self.assertTrue(all(e.event_type.startswith("layla.environment.") for e in recent))

    def test_recent_can_filter_by_exact_event_type(self):
        bus = EventBus()
        buffer = EnvironmentalEventBuffer(bus)
        bus.publish("layla.environment.battery", {"value": 50}, "test")
        bus.publish("layla.environment.system_load", {"value": 80}, "test")

        battery_only = buffer.recent(event_type="layla.environment.battery")
        self.assertEqual(len(battery_only), 1)
        self.assertEqual(battery_only[0].payload["value"], 50)

    def test_buffer_is_bounded(self):
        bus = EventBus()
        buffer = EnvironmentalEventBuffer(bus, max_events=3)
        for i in range(10):
            bus.publish("layla.environment.system_load", {"value": i}, "test")
        self.assertEqual(len(buffer.recent()), 3)
        # Only the most recent 3 survive.
        self.assertEqual([e.payload["value"] for e in buffer.recent()], [7, 8, 9])


class TestEnvironmentalChangeEvaluator(unittest.TestCase):
    def test_network_lost_event_produces_an_observe_level_trigger(self):
        bus = EventBus()
        buffer = EnvironmentalEventBuffer(bus)
        evaluator = EnvironmentalChangeEvaluator(buffer)
        bus.publish("layla.environment.network_connectivity", {"value": False}, "test")

        triggers = evaluator(engine=None)

        self.assertEqual(len(triggers), 1)
        self.assertEqual(triggers[0].action_level, ACTION_OBSERVE)
        self.assertIn("Network connectivity was lost", triggers[0].description)

    def test_network_restored_event_produces_no_trigger(self):
        bus = EventBus()
        buffer = EnvironmentalEventBuffer(bus)
        evaluator = EnvironmentalChangeEvaluator(buffer)
        bus.publish("layla.environment.network_connectivity", {"value": True}, "test")

        triggers = evaluator(engine=None)
        self.assertEqual(triggers, [])

    def test_the_same_event_is_never_triggered_twice(self):
        """Structural retry-storm prevention: calling the evaluator
        repeatedly (as ProactiveEngine.evaluate() does on every real
        tick) must not keep re-emitting the same historical event.
        """
        bus = EventBus()
        buffer = EnvironmentalEventBuffer(bus)
        evaluator = EnvironmentalChangeEvaluator(buffer)
        bus.publish("layla.environment.network_connectivity", {"value": False}, "test")

        first = evaluator(engine=None)
        second = evaluator(engine=None)
        third = evaluator(engine=None)

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(third, [])

    def test_a_new_event_after_a_seen_one_still_triggers(self):
        bus = EventBus()
        buffer = EnvironmentalEventBuffer(bus)
        evaluator = EnvironmentalChangeEvaluator(buffer)
        bus.publish("layla.environment.network_connectivity", {"value": False}, "test")
        evaluator(engine=None)

        bus.publish("layla.environment.network_connectivity", {"value": False}, "test")  # a second, distinct loss event
        second_batch = evaluator(engine=None)

        self.assertEqual(len(second_batch), 1)

    def test_never_calls_handle_event_or_any_runtime_method(self):
        """Structural proof: engine=None is passed through and never
        touched -- this evaluator cannot itself drive an action.
        """
        bus = EventBus()
        buffer = EnvironmentalEventBuffer(bus)
        evaluator = EnvironmentalChangeEvaluator(buffer)
        bus.publish("layla.environment.network_connectivity", {"value": False}, "test")
        # engine=None would raise AttributeError if the evaluator tried
        # to call anything on it.
        evaluator(engine=None)


if __name__ == "__main__":
    unittest.main()
