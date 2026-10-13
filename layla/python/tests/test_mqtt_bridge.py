"""Real MQTTBridge tests. Runs a real, minimal, in-repo MQTT 3.1.1
broker (this test's own fixture -- a genuine binary wire-protocol
implementation, not a mock of `paho-mqtt`) and has the real bridge
genuinely speak MQTT to it: real CONNECT/CONNACK, real PUBLISH, real
SUBSCRIBE/SUBACK, real retained-message delivery. Inbound messages are
confirmed to land as real `avishkar_core.EventBus` events.
"""

import time
import unittest

from avishkar_core import EventBus

from avishkar_layla.mqtt.client import MQTT_EVENT_PREFIX, MQTTBridge, topic_matches
from avishkar_layla.mqtt.errors import MQTTNotConnectedError, MQTTPublishNotAllowedError, MQTTSubscribeNotAllowedError

# Plain top-level import, not a package-relative one: this repo's
# documented test command (`python -m unittest discover -s
# layla/python/tests`, README.md Testing Guide) discovers this
# directory as a flat set of top-level modules (it adds
# layla/python/tests itself to sys.path), NOT as the layla.python.tests
# package -- a relative import here works when a test is run via its
# full dotted path but fails ("no known parent package") under the
# actual discover command. Confirmed by running the full suite.
from _minimal_mqtt_broker import MinimalMQTTBroker


class TestTopicMatching(unittest.TestCase):
    def test_exact_match(self):
        self.assertTrue(topic_matches("home/kitchen/light", "home/kitchen/light"))

    def test_single_level_wildcard(self):
        self.assertTrue(topic_matches("home/+/light", "home/kitchen/light"))
        self.assertFalse(topic_matches("home/+/light", "home/kitchen/hallway/light"))

    def test_multi_level_wildcard(self):
        self.assertTrue(topic_matches("home/#", "home/kitchen/light"))
        self.assertTrue(topic_matches("home/#", "home"))

    def test_no_match(self):
        self.assertFalse(topic_matches("home/kitchen/light", "home/bedroom/light"))


class RealMQTTBrokerTestCase(unittest.TestCase):
    def setUp(self):
        self.broker = MinimalMQTTBroker()
        self.bus = EventBus()

    def tearDown(self):
        self.broker.stop()


class TestMQTTBridgeConnect(RealMQTTBrokerTestCase):
    def test_real_connect_and_disconnect(self):
        bridge = MQTTBridge(self.bus)
        bridge.connect("127.0.0.1", self.broker.port, client_id="test-client")
        self.assertTrue(bridge.is_connected())
        bridge.disconnect()

    def test_publish_before_connect_raises(self):
        bridge = MQTTBridge(self.bus, allowed_publish_topics=("home/#",))
        with self.assertRaises(MQTTNotConnectedError):
            bridge.publish("home/kitchen/light", b"on")

    def test_real_authentication_success(self):
        auth_broker = MinimalMQTTBroker(expected_username="layla", expected_password="secret")
        try:
            bridge = MQTTBridge(self.bus)
            bridge.connect("127.0.0.1", auth_broker.port, username="layla", password="secret")
            self.assertTrue(bridge.is_connected())
            bridge.disconnect()
        finally:
            auth_broker.stop()

    def test_real_authentication_failure_never_connects(self):
        auth_broker = MinimalMQTTBroker(expected_username="layla", expected_password="secret")
        try:
            bridge = MQTTBridge(self.bus)
            with self.assertRaises(MQTTNotConnectedError):
                bridge.connect("127.0.0.1", auth_broker.port, username="layla", password="wrong", timeout_seconds=3.0)
        finally:
            auth_broker.stop()


class TestMQTTBridgePublish(RealMQTTBrokerTestCase):
    def setUp(self):
        super().setUp()
        self.bridge = MQTTBridge(self.bus, allowed_publish_topics=("home/#",))
        self.bridge.connect("127.0.0.1", self.broker.port)

    def tearDown(self):
        self.bridge.disconnect()
        super().tearDown()

    def test_real_publish_reaches_the_real_broker(self):
        self.bridge.publish("home/kitchen/light", b"on")
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and not self.broker.received_publishes:
            time.sleep(0.05)
        self.assertEqual(self.broker.received_publishes, [("home/kitchen/light", b"on")])

    def test_publish_outside_allowlist_is_refused(self):
        with self.assertRaises(MQTTPublishNotAllowedError):
            self.bridge.publish("office/printer/status", b"idle")
        self.assertEqual(self.broker.received_publishes, [])

    def test_publish_with_retain_is_stored_by_the_real_broker(self):
        self.bridge.publish("home/kitchen/light", b"on", retain=True)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and "home/kitchen/light" not in self.broker._retained:
            time.sleep(0.05)
        self.assertEqual(self.broker._retained["home/kitchen/light"], b"on")


class TestMQTTBridgeSubscribeAndEventBus(RealMQTTBrokerTestCase):
    def setUp(self):
        super().setUp()
        self.events = []
        self.bus.subscribe("*", lambda e: self.events.append(e))
        self.publisher = MQTTBridge(self.bus, allowed_publish_topics=("home/#",))
        self.publisher.connect("127.0.0.1", self.broker.port, client_id="publisher")
        self.subscriber = MQTTBridge(self.bus, allowed_subscribe_topics=("home/#",))
        self.subscriber.connect("127.0.0.1", self.broker.port, client_id="subscriber")

    def tearDown(self):
        self.publisher.disconnect()
        self.subscriber.disconnect()
        super().tearDown()

    def test_subscribe_outside_allowlist_is_refused(self):
        with self.assertRaises(MQTTSubscribeNotAllowedError):
            self.subscriber.subscribe("office/#")

    def test_real_end_to_end_publish_to_eventbus(self):
        """The full real chain: subscribe -> real broker forwards a
        real published message -> paho's real on_message callback ->
        a real EventBus event, all over a genuine MQTT wire-protocol
        connection to the in-repo broker fixture.
        """
        self.subscriber.subscribe("home/kitchen/+")
        time.sleep(0.3)  # let the real SUBSCRIBE/SUBACK round trip land

        self.publisher.publish("home/kitchen/light", b"on")

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not self.events:
            time.sleep(0.05)

        matching = [e for e in self.events if e.event_type == f"{MQTT_EVENT_PREFIX}home/kitchen/light"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].payload["topic"], "home/kitchen/light")
        self.assertEqual(matching[0].payload["payload"], b"on")
        self.assertEqual(matching[0].source, "mqtt")

    def test_retained_message_delivered_on_new_subscribe(self):
        """Reuses the already-connected `self.subscriber` (from setUp)
        as the "late" subscriber instead of opening a third real
        connection -- still a genuine real-broker retained-delivery
        test, just without the extra connect/disconnect overhead.
        """
        self.publisher.publish("home/kitchen/light", b"on", retain=True)
        time.sleep(0.3)

        self.subscriber.subscribe("home/kitchen/light")

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not self.events:
            time.sleep(0.05)

        matching = [e for e in self.events if e.event_type == f"{MQTT_EVENT_PREFIX}home/kitchen/light"]
        self.assertEqual(len(matching), 1)
        self.assertTrue(matching[0].payload["retain"])


if __name__ == "__main__":
    unittest.main()
