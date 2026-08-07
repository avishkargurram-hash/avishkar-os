import unittest

from avishkar_core import EventBus


class TestEventBusPublishSubscribe(unittest.TestCase):
    def test_subscriber_receives_published_event(self):
        bus = EventBus()
        received = []
        bus.subscribe("agent.task.completed", received.append)

        event = bus.publish("agent.task.completed", {"task_id": "t-1"}, source="test")

        self.assertEqual(len(received), 1)
        self.assertIs(received[0], event)
        self.assertEqual(event.event_type, "agent.task.completed")
        self.assertEqual(event.payload, {"task_id": "t-1"})
        self.assertEqual(event.source, "test")
        self.assertTrue(event.event_id)
        self.assertTrue(event.timestamp)

    def test_unrelated_event_type_not_delivered(self):
        bus = EventBus()
        received = []
        bus.subscribe("agent.task.completed", received.append)

        bus.publish("agent.task.failed", {}, source="test")

        self.assertEqual(received, [])

    def test_multiple_subscribers_called_in_order(self):
        bus = EventBus()
        call_order = []
        bus.subscribe("x", lambda e: call_order.append("first"))
        bus.subscribe("x", lambda e: call_order.append("second"))

        bus.publish("x", {}, source="test")

        self.assertEqual(call_order, ["first", "second"])

    def test_wildcard_subscriber_receives_every_event(self):
        bus = EventBus()
        received_types = []
        bus.subscribe("*", lambda e: received_types.append(e.event_type))

        bus.publish("a.b", {}, source="test")
        bus.publish("c.d", {}, source="test")

        self.assertEqual(received_types, ["a.b", "c.d"])

    def test_unsubscribe_stops_delivery(self):
        bus = EventBus()
        received = []
        subscription = bus.subscribe("x", received.append)
        bus.unsubscribe(subscription)

        bus.publish("x", {}, source="test")

        self.assertEqual(received, [])


class TestEventBusHandlerIsolation(unittest.TestCase):
    def test_one_handler_raising_does_not_stop_others(self):
        bus = EventBus()
        received = []

        def bad_handler(event):
            raise RuntimeError("handler exploded")

        bus.subscribe("x", bad_handler)
        bus.subscribe("x", received.append)

        # Must not raise -- the bad handler's exception is caught and logged.
        event = bus.publish("x", {}, source="test")

        self.assertEqual(received, [event])

    def test_publish_returns_event_even_if_all_handlers_fail(self):
        bus = EventBus()

        def always_fails(event):
            raise RuntimeError("nope")

        bus.subscribe("x", always_fails)
        event = bus.publish("x", {"k": "v"}, source="test")

        self.assertEqual(event.payload, {"k": "v"})


if __name__ == "__main__":
    unittest.main()
