"""MQTTBridge -- real `paho-mqtt` client wrapper. See CONTRACT.md SS42.

STATUS: REAL. Genuinely connects to a real MQTT broker via
`paho.mqtt.client.Client` (VERSION2 callback API), with real
authentication, real TLS support, real QoS/retained-message publish,
real subscribe, and real automatic reconnect (paho's own
`reconnect_delay_set`, not reimplemented here). Verified in
`test_mqtt_bridge.py` against a real, minimal, in-repo MQTT 3.1.1
broker this suite runs itself -- a genuine binary MQTT wire-protocol
conversation (CONNECT/CONNACK, PUBLISH, SUBSCRIBE/SUBACK,
PINGREQ/PINGRESP), the same "real local fixture" discipline
`test_smtp_email_transport.py`/`test_home_assistant_executor.py`
established, extended here to a binary protocol rather than a text
one.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional, Sequence

from avishkar_core import EventBus

from .errors import MQTTNotConnectedError, MQTTPublishNotAllowedError, MQTTSubscribeNotAllowedError

MQTT_EVENT_PREFIX = "layla.mqtt."


def topic_matches(topic_filter: str, topic: str) -> bool:
    """Real MQTT 3.1.1 topic-matching semantics (spec section 4.7):
    '+' matches exactly one topic level; '#' (valid only as the final
    character) matches any number of trailing levels, including zero.
    """
    filter_levels = topic_filter.split("/")
    topic_levels = topic.split("/")
    for i, level in enumerate(filter_levels):
        if level == "#":
            return True
        if i >= len(topic_levels):
            return False
        if level != "+" and level != topic_levels[i]:
            return False
    return len(filter_levels) == len(topic_levels)


def _allowed(topic: str, patterns: Sequence[str]) -> bool:
    return any(topic_matches(pattern, topic) for pattern in patterns)


class MQTTBridge:
    def __init__(
        self, event_bus: EventBus, *, allowed_publish_topics: Sequence[str] = (),
        allowed_subscribe_topics: Sequence[str] = (), source: str = "mqtt",
        client_factory: Optional[Callable[[Optional[str]], Any]] = None,
    ) -> None:
        self._event_bus = event_bus
        self._allowed_publish = tuple(allowed_publish_topics)
        self._allowed_subscribe = tuple(allowed_subscribe_topics)
        self._source = source
        self._client_factory = client_factory or self._real_client_factory
        self._client: Optional[Any] = None
        self._connected_event = threading.Event()

    def _real_client_factory(self, client_id: Optional[str]) -> Any:
        import paho.mqtt.client as mqtt

        return mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=client_id or "",
        )

    def connect(
        self, host: str, port: int = 1883, *, username: Optional[str] = None, password: Optional[str] = None,
        use_tls: bool = False, keepalive: int = 60, client_id: Optional[str] = None, timeout_seconds: float = 10.0,
        reconnect_min_delay: float = 1.0, reconnect_max_delay: float = 30.0,
    ) -> None:
        self._client = self._client_factory(client_id)
        if username is not None:
            self._client.username_pw_set(username, password)
        if use_tls:
            self._client.tls_set()

        self._connected_event.clear()

        def _on_connect(client, userdata, flags, reason_code, properties=None) -> None:  # pragma: no cover -- paho callback thread
            # paho-mqtt 2.x's VERSION2 callback API passes a real
            # `ReasonCode` object here, not a plain int -- `is_failure`
            # is its own documented way to check success, found by
            # inspecting the installed library after `int(reason_code)`
            # raised a real TypeError during this module's own test run.
            if not reason_code.is_failure:
                self._connected_event.set()

        def _on_message(client, userdata, message) -> None:  # pragma: no cover -- paho callback thread
            self._event_bus.publish(
                f"{MQTT_EVENT_PREFIX}{message.topic}",
                {"topic": message.topic, "payload": message.payload, "qos": message.qos, "retain": bool(message.retain)},
                self._source,
            )

        self._client.on_connect = _on_connect
        self._client.on_message = _on_message
        # Real automatic reconnect -- paho's own backoff, not reimplemented.
        self._client.reconnect_delay_set(min_delay=reconnect_min_delay, max_delay=reconnect_max_delay)

        self._client.connect(host, port, keepalive=keepalive)
        self._client.loop_start()

        if not self._connected_event.wait(timeout=timeout_seconds):
            self._client.loop_stop()
            raise MQTTNotConnectedError(f"MQTT CONNACK not received from {host}:{port} within {timeout_seconds}s")

    def is_connected(self) -> bool:
        return self._client is not None and self._connected_event.is_set()

    def _require_connected(self) -> None:
        if not self.is_connected():
            raise MQTTNotConnectedError("MQTTBridge.connect() has not succeeded -- no active broker connection")

    def publish(self, topic: str, payload: Any, *, qos: int = 0, retain: bool = False):
        self._require_connected()
        if not _allowed(topic, self._allowed_publish):
            raise MQTTPublishNotAllowedError(
                f"publish to topic {topic!r} is not in this bridge's allowlist {self._allowed_publish!r} -- "
                f"fail closed, no default allowlist"
            )
        result = self._client.publish(topic, payload, qos=qos, retain=retain)
        result.wait_for_publish(timeout=10.0)
        return result

    def subscribe(self, topic_filter: str, *, qos: int = 0) -> None:
        self._require_connected()
        if not _allowed(topic_filter, self._allowed_subscribe):
            raise MQTTSubscribeNotAllowedError(
                f"subscribe to {topic_filter!r} is not in this bridge's allowlist {self._allowed_subscribe!r} -- "
                f"fail closed, no default allowlist"
            )
        self._client.subscribe(topic_filter, qos=qos)

    def disconnect(self) -> None:
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()
            self._connected_event.clear()
