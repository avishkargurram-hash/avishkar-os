"""Two ProtocolAdapters that let Layla control real relay hardware over MQTT,
gated by Layla's normal risk/approval pipeline.

MqttHomeAdapter -- for a bespoke `TvMqtt` firmware protocol:
    cmd    tryvanta/home/<id>/relay/<n>/set     on|off|toggle   (n = 1..4 or "all")
    state  tryvanta/home/<id>/relay/<n>/state   on|off          (retained)
    avail  tryvanta/home/<id>/status            online|offline  (retained, LWT)
Proven against a mock box (prove_home_tool.py / prove_home_loop.py) but that
bespoke firmware was never actually written -- kept, untouched, in case it
ever is; not what's registered against the real device below.

EspHomeSwitchboardAdapter (2026-09-14) -- for the REAL, physically-flashed
ESPHome relay box, which speaks ESPHome's own native MQTT convention
instead (confirmed live against the real device's retained state on the
real broker). See its own class docstring for the exact topic contract.

Both register two tools each (`relay_set`, `relay_status` / `status`) on a
UniversalToolRegistry; every relay_set flows through ToolRuntime ->
risk.classify_risk -> ApprovalManager exactly like any other tool, so "turn
on the porch light" is gate-able, not a raw fire-and-forget.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional, Tuple

from ..errors import ProtocolInvocationError
from ..protocol import ProtocolAdapter
from ..types import ToolContract, ToolExecutionRequest, ToolExecutionResult


class MqttHomeAdapter(ProtocolAdapter):
    protocol_name = "home"

    def __init__(
        self,
        host: str,
        port: int,
        device_id: str = "home-001",
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
            raise ProtocolInvocationError("MqttHomeAdapter requires paho-mqtt") from exc

        self._device = device_id
        self._base = f"tryvanta/home/{device_id}"
        self._state: Dict[int, str] = {}
        self._avail: Optional[str] = None
        self._lock = threading.Lock()

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"layla-home-{device_id}")
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
        c.subscribe(f"{self._base}/relay/+/state", 1)
        c.subscribe(f"{self._base}/status", 1)

    def _on_message(self, c, u, msg):
        with self._lock:
            if msg.topic.endswith("/status"):
                self._avail = msg.payload.decode()
            else:
                try:
                    n = int(msg.topic.split("/")[4])
                    self._state[n] = msg.payload.decode()
                except (ValueError, IndexError):
                    pass

    def _snapshot(self):
        with self._lock:
            return dict(self._state), self._avail

    # -- ProtocolAdapter ---------------------------------------------------
    def discover_tools(self) -> Tuple[ToolContract, ...]:
        return (
            ToolContract(
                identity="relay_set",
                description="Turn a TryvantaHome relay on, off, or toggle it (relay 1-4 or 'all').",
                protocol="home",
                input_schema={
                    "type": "object",
                    "properties": {
                        "relay": {"type": ["integer", "string"], "description": "1-4 or 'all'"},
                        "action": {"type": "string", "enum": ["on", "off", "toggle"]},
                    },
                    "required": ["relay", "action"],
                },
                permissions=("write", "home"),
                auth_requirement="owner",
            ),
            ToolContract(
                identity="relay_status",
                description="Read the current on/off state of every TryvantaHome relay and its availability.",
                protocol="home",
                input_schema={"type": "object"},
                permissions=("read", "home"),
            ),
        )

    def invoke(self, contract: ToolContract, request: ToolExecutionRequest) -> ToolExecutionResult:
        start = time.monotonic()
        inp: Dict[str, Any] = request.input if isinstance(request.input, dict) else {}

        if contract.identity == "relay_status":
            state, avail = self._snapshot()
            return self._ok(contract, {"available": avail, "relays": state}, start)

        # relay_set
        relay = inp.get("relay")
        action = str(inp.get("action", "")).lower()
        if relay is None or action not in ("on", "off", "toggle"):
            return self._err(contract, "relay_set needs relay (1-4|'all') and action (on|off|toggle)", start)

        target = "all" if str(relay).lower() == "all" else relay
        topic = f"{self._base}/relay/{target}/set"
        info = self._client.publish(topic, action, qos=1)
        try:
            info.wait_for_publish(timeout=5)
        except Exception:  # noqa: BLE001
            pass

        time.sleep(0.5)  # let the box echo its new state back
        state, avail = self._snapshot()
        out = {"commanded": {"relay": target, "action": action}, "available": avail, "relays": state}
        if avail is not None and avail != "online":
            out["warning"] = "box reports offline; command was published (retained) and applies on reconnect"
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
        heard from). Public accessor for a background presence monitor --
        avoids a second MQTT client just to watch for online/offline transitions.
        """
        return self._snapshot()[1]


class EspHomeSwitchboardAdapter(ProtocolAdapter):
    """ProtocolAdapter for the REAL, physically-flashed ESPHome relay box
    (2026-09-14) -- MqttHomeAdapter above was built for a bespoke `TvMqtt`
    firmware protocol that was never actually written; the switchboard the
    founder built and flashed instead runs stock ESPHome, which speaks its
    own native MQTT convention (confirmed live against the real device's
    retained state on the real broker):
        cmd    tryvanta/<prefix>/switch/<slug>/command      ON|OFF   (uppercase; no native toggle)
        state  tryvanta/<prefix>/switch/<slug>/state        ON|OFF   (retained)
        sensor tryvanta/<prefix>/binary_sensor/<slug>/state ON|OFF   (retained, read-only)
        avail  tryvanta/<prefix>/status                     online|offline  (retained, LWT)

    <slug> is whatever ESPHome derives from each component's configured
    `name` (e.g. "Relay 6" -> "relay_6") -- not assumed here, only ever
    learned from real retained messages actually seen on the wire, so this
    adapter works unmodified regardless of how many relays/sensors exist or
    what they're named. Kept as a separate class from MqttHomeAdapter (not a
    parameter on it) so the original, already-proven adapter is untouched.

    Two tools, same gated pattern as MqttHomeAdapter:
        switchboard:relay_set     {"relay": "<slug>|<number>|'all'", "action": "on"|"off"|"toggle"}
        switchboard:status        {}   (relays AND binary sensors)
    """

    protocol_name = "switchboard"

    def __init__(
        self,
        host: str,
        port: int,
        topic_prefix: str = "switchboard1",
        *,
        username: Optional[str] = None,
        password: Optional[str] = None,
        tls: bool = False,
        cafile: Optional[str] = None,
        settle_seconds: float = 1.0,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:  # pragma: no cover
            raise ProtocolInvocationError("EspHomeSwitchboardAdapter requires paho-mqtt") from exc

        self._base = f"tryvanta/{topic_prefix}"
        self._relays: Dict[str, str] = {}
        self._sensors: Dict[str, str] = {}
        self._avail: Optional[str] = None
        self._lock = threading.Lock()
        # What each relay slug physically controls (2026-09-15, the founder's
        # own real wiring) -- purely descriptive/resolution data, never
        # affects the wire protocol. relay_status echoes it back so Layla can
        # narrate "the fan is on" instead of "relay_1 is ON", and relay_set
        # resolves a label ("fan") to its slug the same way it already
        # resolves a bare number -- optional, empty by default.
        self._labels: Dict[str, str] = dict(labels or {})

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"layla-switchboard-{topic_prefix}")
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
        c.subscribe(f"{self._base}/switch/+/state", 1)
        c.subscribe(f"{self._base}/binary_sensor/+/state", 1)
        c.subscribe(f"{self._base}/status", 1)

    def _on_message(self, c, u, msg):
        with self._lock:
            if msg.topic.endswith("/status"):
                self._avail = msg.payload.decode()
                return
            parts = msg.topic.split("/")  # tryvanta/<prefix>/switch|binary_sensor/<slug>/state
            if len(parts) < 4:
                return
            kind, slug = parts[2], parts[3]
            value = msg.payload.decode()
            if kind == "switch":
                self._relays[slug] = value
            elif kind == "binary_sensor":
                self._sensors[slug] = value

    def _snapshot(self):
        with self._lock:
            return dict(self._relays), dict(self._sensors), self._avail

    def _resolve_slug(self, relay: Any) -> Optional[str]:
        """Accepts an exact slug ("relay_6"), a bare number (6 -> "relay_6"),
        a known label ("fan", exact or substring match against self._labels),
        or anything already matching a currently-known relay -- never invents
        a slug that hasn't actually been observed on the wire."""
        relays, _, _ = self._snapshot()
        s = str(relay).strip().lower()
        if s in relays:
            return s
        candidate = f"relay_{s}"
        if candidate in relays:
            return candidate
        for slug, label in self._labels.items():
            label_l = label.lower()
            if slug in relays and (s == label_l or s in label_l or label_l in s):
                return slug
        return None

    # -- ProtocolAdapter ---------------------------------------------------
    def discover_tools(self) -> Tuple[ToolContract, ...]:
        wiring = (
            " Known wiring: " + "; ".join(f"{slug}={label}" for slug, label in self._labels.items())
            if self._labels else ""
        )
        return (
            ToolContract(
                identity="relay_set",
                description=(
                    "Turn a real switchboard relay on, off, or toggle it. Accepts a relay number, its exact "
                    "slug, or a plain description of what it controls (e.g. 'fan', 'ceiling lights')."
                    + wiring
                ),
                protocol="switchboard",
                input_schema={
                    "type": "object",
                    "properties": {
                        "relay": {"type": ["integer", "string"], "description": "a relay number (e.g. 6), its exact name (e.g. 'relay_6'), what it controls (e.g. 'fan'), or 'all'"},
                        "action": {"type": "string", "enum": ["on", "off", "toggle"]},
                    },
                    "required": ["relay", "action"],
                },
                permissions=("write", "home"),
                auth_requirement="owner",
            ),
            ToolContract(
                identity="relay_status",
                description="Read the current on/off state of every real switchboard relay and sensor, and whether the box is online." + wiring,
                protocol="switchboard",
                input_schema={"type": "object"},
                permissions=("read", "home"),
            ),
        )

    def invoke(self, contract: ToolContract, request: ToolExecutionRequest) -> ToolExecutionResult:
        start = time.monotonic()
        inp: Dict[str, Any] = request.input if isinstance(request.input, dict) else {}

        if contract.identity == "relay_status":
            relays, sensors, avail = self._snapshot()
            labeled = {slug: {"state": state, "label": self._labels.get(slug)} for slug, state in relays.items()}
            return self._ok(contract, {"available": avail, "relays": relays, "relays_labeled": labeled, "sensors": sensors}, start)

        # relay_set
        relay = inp.get("relay")
        action = str(inp.get("action", "")).lower()
        if relay is None or action not in ("on", "off", "toggle"):
            return self._err(contract, "relay_set needs relay (number, name, or 'all') and action (on|off|toggle)", start)

        relays, _, avail = self._snapshot()
        if str(relay).strip().lower() == "all":
            targets = sorted(relays.keys())
        else:
            slug = self._resolve_slug(relay)
            if slug is None:
                known = ", ".join(sorted(relays.keys())) or "(none seen yet -- box may be offline)"
                return self._err(contract, f"unknown relay {relay!r}. Known relays: {known}", start)
            targets = [slug]
        if not targets:
            return self._err(contract, "no relays known yet -- box may be offline", start)

        for slug in targets:
            # ESPHome switches have no native single-topic "toggle" command --
            # computed here from last-known retained state instead.
            if action == "toggle":
                current = relays.get(slug, "OFF")
                payload = "OFF" if current == "ON" else "ON"
            else:
                payload = action.upper()
            info = self._client.publish(f"{self._base}/switch/{slug}/command", payload, qos=1)
            try:
                info.wait_for_publish(timeout=5)
            except Exception:  # noqa: BLE001
                pass

        time.sleep(0.5)  # let the box echo its new state back
        relays, sensors, avail = self._snapshot()
        out = {
            "commanded": {"relay": targets, "labels": [self._labels.get(s, s) for s in targets], "action": action},
            "available": avail, "relays": relays, "sensors": sensors,
        }
        if avail is not None and avail != "online":
            out["warning"] = "box reports offline; command was published (retained) and applies on reconnect"
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
        heard from)."""
        return self._snapshot()[2]
