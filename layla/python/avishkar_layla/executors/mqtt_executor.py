"""Real MQTT executor for EMBODIMENT_MQTT. See CONTRACT.md SS42.

STATUS: REAL. A thin `EmbodimentExecutor`-shaped wrapper
(`(action, parameters) -> output`) around a real, already-connected
`avishkar_layla.mqtt.MQTTBridge`. Registered for `EMBODIMENT_MQTT`,
added to embodiment.py's `_DEFAULT_HIGH_RISK_CAPABILITIES` this same
pass (ADR-0035) -- every action already requires `EmbodimentController`
approval before this executor is even looked up, and `MQTTBridge`
itself additionally enforces its own fail-closed topic allowlists --
two independent, non-redundant gates.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..mqtt.client import MQTTBridge
from .errors import UnknownActionError

_ACTIONS = ("publish", "subscribe")


class MQTTExecutor:
    def __init__(self, bridge: MQTTBridge) -> None:
        self._bridge = bridge

    def __call__(self, action: str, parameters: Mapping[str, Any]) -> Any:
        if action == "publish":
            result = self._bridge.publish(
                parameters["topic"], parameters["payload"], qos=parameters.get("qos", 0),
                retain=parameters.get("retain", False),
            )
            return {"mid": result.mid, "topic": parameters["topic"]}
        if action == "subscribe":
            self._bridge.subscribe(parameters["topic"], qos=parameters.get("qos", 0))
            return {"subscribed": parameters["topic"]}
        raise UnknownActionError(f"MQTTExecutor has no action {action!r} -- expected one of {_ACTIONS}")
