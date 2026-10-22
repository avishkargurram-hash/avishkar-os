"""TuyaFanAdapter -- lets Layla control a real Tuya/Smart-Life cloud device
(the bedroom fan-modular switch) via Tuya's official Cloud API, gated by
Layla's normal risk/approval pipeline exactly like every other tool.

Unlike the ESP32 switchboard (which speaks MQTT directly to a broker Layla
already trusts), this device only speaks Tuya's proprietary local protocol
or Tuya's cloud -- and Layla's brain runs on a remote VPS with no route to
the device's home-network local IP, so the Cloud API (HTTPS, works from
anywhere) is the only viable path, not tinytuya's local_key/LAN discovery.

Confirmed live against the real device (2026-09-22) via tinytuya.Cloud:
  - device id: d7be5923733cd5bd80zdqi, category "fs" (fan switch)
  - real DP codes: "switch" (Boolean), "fan_speed_percent" (Integer 1-5)
  - command endpoint needs the body wrapped as {"commands": [...]} --
    tinytuya.Cloud.sendcommand() posts whatever dict you pass it directly,
    a bare list produces a real "param is illegal" error from Tuya's API.
  - every commanded write was independently confirmed by re-reading
    getstatus() afterward, not just trusting the command endpoint's
    "success": true (same "never fake success" discipline as the ESPHome
    switchboard adapter).
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

from ..errors import ProtocolInvocationError
from ..protocol import ProtocolAdapter
from ..types import ToolContract, ToolExecutionRequest, ToolExecutionResult


class TuyaFanAdapter(ProtocolAdapter):
    protocol_name = "tuya_fan"

    def __init__(
        self,
        access_id: str,
        access_secret: str,
        region: str,
        device_id: str,
        *,
        switch_code: str = "switch",
        speed_code: str = "fan_speed_percent",
        speed_min: int = 1,
        speed_max: int = 5,
    ) -> None:
        try:
            import tinytuya
        except ImportError as exc:  # pragma: no cover
            raise ProtocolInvocationError("TuyaFanAdapter requires tinytuya") from exc

        self._device_id = device_id
        self._switch_code = switch_code
        self._speed_code = speed_code
        self._speed_min = speed_min
        self._speed_max = speed_max
        # One long-lived Cloud client for the service's whole lifetime --
        # tinytuya's own _tuyaplatform() already detects an expired token
        # ("token invalid" in the response) and transparently re-fetches
        # one, so this does not need its own refresh logic on top.
        self._cloud = tinytuya.Cloud(apiRegion=region, apiKey=access_id, apiSecret=access_secret)

    def _get_status(self) -> Optional[Dict[str, Any]]:
        r = self._cloud.getstatus(self._device_id)
        if not isinstance(r, dict) or not r.get("success"):
            return None
        return {item["code"]: item["value"] for item in r.get("result", [])}

    def _offline_reason(self) -> Optional[str]:
        """None when the fan is online (or we could not tell). Otherwise a plain-English reason.

        Tuya's status endpoint keeps returning the LAST value it ever heard ("on", speed 5) for a device that has
        been offline for days, and accepts commands for it with "success". Both are lies as far as the real fan is
        concerned (seen 2026-10-22: the fan switch had been offline since 9 Oct, so "turn it off" reported
        success and Nitya kept warning that it had been on for 100+ hours). Ask Tuya whether it is online first."""
        try:
            r = self._cloud.cloudrequest("/v1.0/devices/" + self._device_id)
            res = (r or {}).get("result") if isinstance(r, dict) and r.get("success") else None
            if not isinstance(res, dict) or res.get("online") is not False:
                return None
            ts = res.get("update_time") or res.get("active_time")
            when = time.strftime("%d %b %H:%M", time.localtime(ts)) if ts else "a long time ago"
            return ("The bedroom fan is OFFLINE (it lost its Wi-Fi/Tuya connection; Tuya last heard from it on "
                    + when + "), so I cannot read or change it until it reconnects. Any 'on/off' value shown "
                    "earlier is stale.")
        except Exception:
            return None

    def discover_tools(self) -> Tuple[ToolContract, ...]:
        return (
            ToolContract(
                identity="fan_set",
                description=(
                    "Turn the real bedroom fan (Tuya fan-modular switch) on, off, or toggle it, "
                    f"and optionally set its speed ({self._speed_min}-{self._speed_max})."
                ),
                protocol="tuya_fan",
                input_schema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["on", "off", "toggle"]},
                        "speed": {"type": "integer", "description": f"{self._speed_min}-{self._speed_max}, optional"},
                    },
                    "required": ["action"],
                },
                permissions=("write", "home"),
                auth_requirement="owner",
            ),
            ToolContract(
                identity="fan_status",
                description="Read the real bedroom fan's current on/off state and speed.",
                protocol="tuya_fan",
                input_schema={"type": "object", "properties": {}},
                permissions=("read", "home"),
            ),
        )

    def invoke(self, contract: ToolContract, request: ToolExecutionRequest) -> ToolExecutionResult:
        start = time.monotonic()
        inp: Dict[str, Any] = request.input if isinstance(request.input, dict) else {}

        if contract.identity in ("fan_status", "fan_set"):
            why = self._offline_reason()
            if why:
                return self._err(contract, why, start)

        if contract.identity == "fan_status":
            status = self._get_status()
            if status is None:
                return self._err(contract, "could not read fan status from Tuya Cloud", start)
            return self._ok(contract, {
                "on": bool(status.get(self._switch_code)),
                "speed": status.get(self._speed_code),
            }, start)

        if contract.identity != "fan_set":
            return self._err(contract, f"unknown tuya_fan tool '{contract.identity}'", start)

        action = str(inp.get("action", "")).lower()
        if action not in ("on", "off", "toggle"):
            return self._err(contract, "fan_set needs action (on|off|toggle)", start)

        before = self._get_status()
        if before is None:
            return self._err(contract, "could not read current fan status from Tuya Cloud", start)

        if action == "toggle":
            new_switch = not bool(before.get(self._switch_code))
        else:
            new_switch = action == "on"

        commands = [{"code": self._switch_code, "value": new_switch}]
        speed = inp.get("speed")
        if speed is not None:
            try:
                speed = max(self._speed_min, min(self._speed_max, int(speed)))
                commands.append({"code": self._speed_code, "value": speed})
            except (TypeError, ValueError):
                pass

        # tinytuya.Cloud.sendcommand() posts whatever we pass it AS the raw
        # body -- Tuya's real API needs it wrapped as {"commands": [...]},
        # confirmed live: a bare list gets "param is illegal" from Tuya.
        result = self._cloud.sendcommand(self._device_id, {"commands": commands})
        if not isinstance(result, dict) or not result.get("success"):
            err = result.get("Payload") if isinstance(result, dict) else "no response"
            return self._err(contract, f"Tuya command failed: {err}", start)

        # Never fake success: re-read real state instead of trusting the
        # command endpoint's own "success": true, same discipline as the
        # ESPHome switchboard adapter.
        time.sleep(0.6)
        after = self._get_status()
        if after is None:
            return self._err(contract, "command sent but could not confirm resulting state", start)

        confirmed = bool(after.get(self._switch_code)) == new_switch
        out = {"commanded": {"action": action, "speed": speed}, "on": bool(after.get(self._switch_code)), "speed": after.get(self._speed_code)}
        if not confirmed:
            out["warning"] = "command sent but device did not report the expected resulting state"
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
        return "healthy" if self._get_status() is not None else "unhealthy"
