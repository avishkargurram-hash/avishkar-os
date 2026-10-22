"""PhoneAgentAdapter -- lets Layla reach a connected Android phone over MQTT,
Tier 1 only (notification, open app, open URL), gated by Layla's normal
risk/approval pipeline exactly like every other tool.

Same shape as PcAgentAdapter and MqttHomeAdapter on purpose: Phone Access is
architecturally just another device connector, not a separate system -- it
speaks the identical cmd/result/status (LWT-driven presence) topic pattern
over the same secured broker. Deliberately narrower than the PC agent's own
already-conservative scope: no SMS, no call, no location, no contacts,
nothing touching Android's most sensitive permission classes -- those wait
for a real approval UI, same discipline already applied to PC Tiers 3/4 and
never revisited casually.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, Optional, Tuple

from ..errors import ProtocolInvocationError
from ..protocol import ProtocolAdapter
from ..types import ToolContract, ToolExecutionRequest, ToolExecutionResult


class PhoneAgentAdapter(ProtocolAdapter):
    protocol_name = "phone"

    def __init__(
        self,
        host: str,
        port: int,
        device_id: str = "phone-001",
        *,
        username: Optional[str] = None,
        password: Optional[str] = None,
        tls: bool = True,
        settle_seconds: float = 1.0,
    ) -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:  # pragma: no cover
            raise ProtocolInvocationError("PhoneAgentAdapter requires paho-mqtt") from exc

        self._device = device_id
        self._base = f"tryvanta/phone/{device_id}"
        self._avail: Optional[str] = None
        self._last_result: Optional[Dict[str, Any]] = None
        self._lock = threading.Lock()

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"layla-phonectl-{device_id}")
        if username:
            self._client.username_pw_set(username, password)
        if tls:
            self._client.tls_set()
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.connect(host, port, 30)
        self._client.loop_start()
        time.sleep(settle_seconds)

    def _on_connect(self, c, u, flags, rc, props=None):
        c.subscribe(f"{self._base}/status", 1)
        c.subscribe(f"{self._base}/result", 1)

    def _on_message(self, c, u, msg):
        with self._lock:
            if msg.topic.endswith("/status"):
                self._avail = msg.payload.decode()
            elif msg.topic.endswith("/result"):
                try:
                    self._last_result = json.loads(msg.payload.decode())
                except Exception:  # noqa: BLE001
                    pass

    def available(self) -> Optional[str]:
        with self._lock:
            return self._avail

    def discover_tools(self) -> Tuple[ToolContract, ...]:
        return (
            ToolContract(
                identity="notify",
                description="Show a notification on the owner's phone with a short message.",
                protocol="phone",
                input_schema={"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]},
                permissions=("write", "phone"),
            ),
            ToolContract(
                identity="open_url",
                description="Open a website in the default browser on the owner's phone.",
                protocol="phone",
                input_schema={"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
                permissions=("write", "phone"),
            ),
            ToolContract(
                identity="open_app",
                description="Launch an app on the owner's phone by its common name (e.g. 'camera', 'maps', "
                            "'gmail', 'phone', 'settings', 'whatsapp').",
                protocol="phone",
                input_schema={"type": "object", "properties": {"app": {"type": "string"}}, "required": ["app"]},
                permissions=("write", "phone"),
            ),
            ToolContract(
                identity="status",
                description="Check whether the owner's phone agent is currently connected.",
                protocol="phone",
                input_schema={"type": "object", "properties": {}},
                permissions=("read", "phone"),
            ),
        )

    def invoke(self, contract: ToolContract, request: ToolExecutionRequest) -> ToolExecutionResult:
        start = time.monotonic()
        inp: Dict[str, Any] = request.input if isinstance(request.input, dict) else {}

        if contract.identity == "status":
            avail = self.available()
            return self._ok(contract, {"available": avail}, start)

        if contract.identity not in ("notify", "open_url", "open_app"):
            return self._err(contract, f"unknown phone tool '{contract.identity}'", start)

        arg_key = {"notify": "message", "open_url": "url", "open_app": "app"}[contract.identity]
        arg = inp.get(arg_key, "")
        if not arg:
            return self._err(contract, f"{contract.identity} needs '{arg_key}'", start)

        with self._lock:
            self._last_result = None
        self._client.publish(f"{self._base}/cmd/{contract.identity}", arg, qos=1)

        deadline = time.time() + 6
        while time.time() < deadline:
            with self._lock:
                if self._last_result and self._last_result.get("cmd") == contract.identity:
                    r = self._last_result
                    break
            time.sleep(0.15)
        else:
            avail = self.available()
            note = "" if avail == "online" else " (phone agent appears offline -- command queued but not confirmed)"
            return self._ok(contract, {"published": True, "note": f"no confirmation yet{note}"}, start)

        status = "success" if r.get("status") == "success" else "error"
        return ToolExecutionResult(
            tool_identity=contract.identity, protocol=self.protocol_name, status=status,
            output=r.get("detail") if status == "success" else None,
            error=r.get("detail") if status == "error" else None,
            latency_ms=(time.monotonic() - start) * 1000, attempts=1,
        )

    def _ok(self, contract, output, start):
        return ToolExecutionResult(
            tool_identity=contract.identity, protocol=self.protocol_name, status="success",
            output=output, latency_ms=(time.monotonic() - start) * 1000, attempts=1,
        )

    def _err(self, contract, msg, start):
        return ToolExecutionResult(
            tool_identity=contract.identity, protocol=self.protocol_name, status="error",
            error=msg, latency_ms=(time.monotonic() - start) * 1000, attempts=1,
        )

    def health_check(self) -> str:
        return "healthy" if self.available() == "online" else "unhealthy"
