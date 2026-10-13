"""MqttRobotAdapter -- a ProtocolAdapter that lets Layla drive the Tryvanta
Robot ESP32 motor controller over MQTT, gated by Layla's normal risk/approval
pipeline. Same pattern as MqttHomeAdapter (home_control.py) and PcAgentAdapter
(pc_agent.py) -- outbound-only MQTT, one adapter per device family, dedicated
per-device credentials.

Topic contract (matches TryvantaRobot.ino's MQTT bridge):
    cmd    tryvanta/robot/<id>/motor/set     JSON {action,speed,duration_ms}
    state  tryvanta/robot/<id>/motor/state   JSON {action,speed}  (retained)
    avail  tryvanta/robot/<id>/status        online|offline        (retained, LWT)

Two tools:
    robot:move    {"action":"forward|backward|left|right","speed":0-255,
                    "duration_ms":N}   (write, robot, auth=owner)
    robot:stop    {}                                                (write, robot)
    robot:status  {}                                                (read, robot)

"stop" is its own tool (not folded into "move" with action=stop) so it can be
called with zero ambiguity in an emergency -- deliberately the same instinct
as TryvantaHome's boot-safe-off default: the safe action should never require
getting an argument right.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, Optional, Tuple

from ..errors import ProtocolInvocationError
from ..protocol import ProtocolAdapter
from ..types import ToolContract, ToolExecutionRequest, ToolExecutionResult

_VALID_ACTIONS = ("forward", "backward", "left", "right")


class MqttRobotAdapter(ProtocolAdapter):
    protocol_name = "robot"

    def __init__(
        self,
        host: str,
        port: int,
        device_id: str = "robot-001",
        *,
        username: Optional[str] = None,
        password: Optional[str] = None,
        tls: bool = False,
        cafile: Optional[str] = None,
        settle_seconds: float = 1.0,
    ) -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:  # pragma: no cover
            raise ProtocolInvocationError("MqttRobotAdapter requires paho-mqtt") from exc

        self._device = device_id
        self._base = f"tryvanta/robot/{device_id}"
        self._motor_state: Dict[str, Any] = {}
        self._avail: Optional[str] = None
        self._lock = threading.Lock()

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"layla-robot-{device_id}")
        if username:
            self._client.username_pw_set(username, password)
        if tls:
            self._client.tls_set(ca_certs=cafile)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.connect(host, port, 30)
        self._client.loop_start()
        time.sleep(settle_seconds)  # let retained state arrive

    # -- mqtt callbacks ----------------------------------------------------
    def _on_connect(self, c, u, flags, rc, props=None):
        c.subscribe(f"{self._base}/motor/state", 1)
        c.subscribe(f"{self._base}/status", 1)

    def _on_message(self, c, u, msg):
        with self._lock:
            if msg.topic.endswith("/status"):
                self._avail = msg.payload.decode()
            elif msg.topic.endswith("/motor/state"):
                try:
                    self._motor_state = json.loads(msg.payload.decode())
                except (ValueError, UnicodeDecodeError):
                    pass

    def _snapshot(self):
        with self._lock:
            return dict(self._motor_state), self._avail

    def _publish_set(self, action: str, speed: Optional[int], duration_ms: Optional[int]):
        payload: Dict[str, Any] = {"action": action}
        if speed is not None:
            payload["speed"] = speed
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        info = self._client.publish(f"{self._base}/motor/set", json.dumps(payload), qos=1)
        try:
            info.wait_for_publish(timeout=5)
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.4)  # let the robot echo its new state back

    # -- ProtocolAdapter ---------------------------------------------------
    def discover_tools(self) -> Tuple[ToolContract, ...]:
        return (
            ToolContract(
                identity="move",
                description=(
                    "Drive the Tryvanta Robot: forward, backward, left, or right, "
                    "for an optional duration in milliseconds. If duration_ms is "
                    "omitted the robot keeps moving until told to stop (or a "
                    "built-in safety watchdog stops it after ~2s with no new "
                    "command)."
                ),
                protocol="robot",
                input_schema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": list(_VALID_ACTIONS)},
                        "speed": {"type": "integer", "minimum": 0, "maximum": 255},
                        "duration_ms": {"type": "integer", "minimum": 0},
                    },
                    "required": ["action"],
                },
                permissions=("write", "robot"),
                auth_requirement="owner",
            ),
            ToolContract(
                identity="stop",
                description="Immediately stop the Tryvanta Robot's motors. Always safe to call.",
                protocol="robot",
                input_schema={"type": "object"},
                permissions=("write", "robot"),
            ),
            ToolContract(
                identity="status",
                description="Read the Tryvanta Robot's current motor state and online/offline availability.",
                protocol="robot",
                input_schema={"type": "object"},
                permissions=("read", "robot"),
            ),
        )

    def invoke(self, contract: ToolContract, request: ToolExecutionRequest) -> ToolExecutionResult:
        start = time.monotonic()
        inp: Dict[str, Any] = request.input if isinstance(request.input, dict) else {}

        if contract.identity == "status":
            state, avail = self._snapshot()
            return self._ok(contract, {"available": avail, "motor": state}, start)

        if contract.identity == "stop":
            self._publish_set("stop", None, None)
            state, avail = self._snapshot()
            return self._ok(contract, {"commanded": "stop", "available": avail, "motor": state}, start)

        # move
        action = str(inp.get("action", "")).lower()
        if action not in _VALID_ACTIONS:
            return self._err(contract, f"move needs action to be one of {_VALID_ACTIONS}", start)
        speed = inp.get("speed")
        duration_ms = inp.get("duration_ms")
        self._publish_set(action, speed, duration_ms)
        state, avail = self._snapshot()
        out = {
            "commanded": {"action": action, "speed": speed, "duration_ms": duration_ms},
            "available": avail,
            "motor": state,
        }
        if avail is not None and avail != "online":
            out["warning"] = "robot reports offline; command was published and will NOT be acted on until it reconnects"
        return self._ok(contract, out, start)

    def _ok(self, contract, output, start):
        return ToolExecutionResult(
            tool_identity=contract.identity, protocol=self.protocol_name,
            status="success", output=output,
            latency_ms=(time.monotonic() - start) * 1000, attempts=1,
        )

    def _err(self, contract, msg, start):
        return ToolExecutionResult(
            tool_identity=contract.identity, protocol=self.protocol_name,
            status="error", error=msg,
            latency_ms=(time.monotonic() - start) * 1000, attempts=1,
        )

    def health_check(self) -> str:
        return "healthy" if self._client.is_connected() else "unhealthy"

    def available(self) -> Optional[str]:
        """Last-known retained availability ("online"/"offline"/None if never
        heard from). Public accessor, mirrors MqttHomeAdapter.available()."""
        return self._snapshot()[1]
