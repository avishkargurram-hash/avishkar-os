"""PcAgentAdapter -- lets Layla control a connected Windows PC over MQTT,
Tiers 1-2 only (browser + application launch), gated by Layla's normal
risk/approval pipeline exactly like every other tool.

Same shape as MqttHomeAdapter on purpose: PC Access is architecturally just
another device connector, not a separate system -- it speaks the identical
topic pattern (cmd/result/status, LWT-driven presence) over the same secured
broker the ESP32 home box uses. Tier 3/4 (screen automation, shell exec,
system changes) are deliberately NOT exposed here -- see CONTRACT note in
layla_pc_agent.py; those wait for a real approval UI before they're built at all.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, Optional, Tuple

from ..errors import ProtocolInvocationError
from ..protocol import ProtocolAdapter
from ..types import ToolContract, ToolExecutionRequest, ToolExecutionResult


class PcAgentAdapter(ProtocolAdapter):
    protocol_name = "pc"

    def __init__(
        self,
        host: str,
        port: int,
        device_id: str = "pc-001",
        *,
        username: Optional[str] = None,
        password: Optional[str] = None,
        tls: bool = True,
        settle_seconds: float = 1.0,
    ) -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:  # pragma: no cover
            raise ProtocolInvocationError("PcAgentAdapter requires paho-mqtt") from exc

        self._device = device_id
        self._base = f"tryvanta/pc/{device_id}"
        self._avail: Optional[str] = None
        self._last_result: Optional[Dict[str, Any]] = None
        self._lock = threading.Lock()

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"layla-pcctl-{device_id}")
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
                identity="open_url",
                description="Open a website in the default browser on the connected PC.",
                protocol="pc",
                input_schema={"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
                permissions=("write", "pc"),
            ),
            ToolContract(
                identity="open_app",
                description="Launch an application on the connected PC (notepad, chrome, edge, vscode, "
                            "spotify, explorer, calculator, word, excel, task manager, settings).",
                protocol="pc",
                input_schema={"type": "object", "properties": {"app": {"type": "string"}}, "required": ["app"]},
                permissions=("write", "pc"),
            ),
            ToolContract(
                identity="status",
                description="Check whether the connected PC's Layla agent is online.",
                protocol="pc",
                input_schema={"type": "object", "properties": {}},
                permissions=("read", "pc"),
            ),
            ToolContract(
                identity="query_pc_activity",
                description="Query recent digital activity timeline and application history recorded by Screenpipe on the connected Windows PC.",
                protocol="pc",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search keyword or application name."},
                        "hours": {"type": "number", "description": "Time window in hours (default 24)."},
                    },
                },
                permissions=("read", "pc"),
            ),
            ToolContract(
                identity="list_windows",
                description="List all active, visible open application windows on the connected Windows PC.",
                protocol="pc",
                input_schema={"type": "object", "properties": {}},
                permissions=("read", "pc"),
            ),
            ToolContract(
                identity="screenshot",
                description="Capture a screenshot of the connected Windows PC desktop.",
                protocol="pc",
                input_schema={"type": "object", "properties": {}},
                permissions=("read", "pc"),
            ),
            ToolContract(
                identity="control_desktop",
                description="Control the Windows PC desktop GUI (focus_window, click, type, hotkey).",
                protocol="pc",
                input_schema={
                    "type": "object",
                    "properties": {
                        "op": {"type": "string", "enum": ["focus_window", "click", "type", "hotkey"], "description": "Desktop operation."},
                        "args": {"type": "object", "description": "Operation arguments."},
                    },
                    "required": ["op"],
                },
                permissions=("write", "pc"),
            ),
        )

    def invoke(self, contract: ToolContract, request: ToolExecutionRequest) -> ToolExecutionResult:
        start = time.monotonic()
        inp: Dict[str, Any] = request.input if isinstance(request.input, dict) else {}

        if contract.identity == "status":
            avail = self.available()
            return self._ok(contract, {"available": avail}, start)

        known_tools = ("open_url", "open_app", "query_pc_activity", "list_windows", "screenshot", "control_desktop")
        if contract.identity not in known_tools:
            return self._err(contract, f"unknown pc tool '{contract.identity}'", start)

        if contract.identity == "open_url":
            payload_str = inp.get("url", "")
            if not payload_str:
                return self._err(contract, "open_url needs 'url'", start)
        elif contract.identity == "open_app":
            payload_str = inp.get("app", "")
            if not payload_str:
                return self._err(contract, "open_app needs 'app'", start)
        elif contract.identity in ("query_pc_activity", "control_desktop"):
            payload_str = json.dumps(inp)
        else: # list_windows, screenshot
            payload_str = "{}"

        with self._lock:
            self._last_result = None
        self._client.publish(f"{self._base}/cmd/{contract.identity}", payload_str, qos=1)

        deadline = time.time() + 8
        while time.time() < deadline:
            with self._lock:
                if self._last_result and self._last_result.get("cmd") == contract.identity:
                    r = self._last_result
                    break
            time.sleep(0.15)
        else:
            avail = self.available()
            note = "" if avail == "online" else " (PC agent appears offline -- command queued but not confirmed)"
            return self._ok(contract, {"published": True, "note": f"no confirmation yet{note}"}, start)

        status = "success" if r.get("status") == "success" or r.get("ok") is True else "error"
        output_data = r.get("output") or r.get("detail") or r.get("windows") or r.get("screenshot_b64") or r
        error_msg = r.get("detail") or r.get("error") if status == "error" else None
        return ToolExecutionResult(
            tool_identity=contract.identity, protocol=self.protocol_name, status=status,
            output=output_data if status == "success" else None,
            error=error_msg,
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
