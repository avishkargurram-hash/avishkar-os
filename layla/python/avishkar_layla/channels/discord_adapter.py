"""DiscordChannelAdapter -- a real avishkar_integration.ProtocolAdapter
implementation for Discord. See CONTRACT.md SS37.

STATUS: ADAPTER READY / REQUIRES EXTERNAL CREDENTIALS -- same pattern
as the other channel adapters. `DiscordBotAPITransport` is a REAL HTTP
client against Discord's real Bot REST API; no bot token is configured
in this environment.
"""

from __future__ import annotations

import os
import time
from typing import Callable, Dict, Sequence, Tuple

from avishkar_integration import ProtocolInvocationError, ToolContract, ToolExecutionRequest, ToolExecutionResult
from avishkar_integration.protocol import ProtocolAdapter

# (to, body) -> message_id. `to` is a Discord channel ID.
DiscordTransport = Callable[[str, str], str]


def _unconfigured_transport(to: str, body: str) -> str:
    raise ProtocolInvocationError(
        "DiscordChannelAdapter has no real transport configured -- this is the documented "
        "ADAPTER READY / REQUIRES EXTERNAL CREDENTIALS boundary (CONTRACT.md SS37): wire a real "
        "Discord Bot API-backed transport before using this adapter in production."
    )


class DiscordChannelAdapter(ProtocolAdapter):
    protocol_name = "discord"

    def __init__(self, tools: Sequence[ToolContract] = (), *, transport: DiscordTransport = _unconfigured_transport) -> None:
        self._tools: Dict[str, ToolContract] = {t.identity: t for t in tools}
        self._transport = transport

    def register_tool(self, contract: ToolContract) -> None:
        self._tools[contract.identity] = contract

    def discover_tools(self) -> Tuple[ToolContract, ...]:
        return tuple(self._tools.values())

    def invoke(self, contract: ToolContract, request: ToolExecutionRequest) -> ToolExecutionResult:
        payload = request.input or {}
        to = payload.get("to")
        body = payload.get("body", "")
        if not to:
            raise ProtocolInvocationError("discord tool call missing required 'to' field in input")

        start = time.monotonic()
        try:
            message_id = self._transport(to, body)
        except ProtocolInvocationError:
            raise
        except Exception as exc:  # noqa: BLE001 -- normalized into our own hierarchy
            raise ProtocolInvocationError(f"discord send to '{to}' failed: {exc}") from exc
        elapsed_ms = (time.monotonic() - start) * 1000

        return ToolExecutionResult(
            tool_identity=contract.identity, protocol=self.protocol_name, status="success",
            output={"message_id": message_id}, latency_ms=elapsed_ms,
        )


class DiscordBotAPITransport:
    """REAL HTTP client for Discord's real Bot REST API
    (`POST https://discord.com/api/v10/channels/{channel_id}/messages`).
    """

    def __init__(self, *, api_version: str = "v10", token_env: str = "DISCORD_BOT_TOKEN", timeout_seconds: float = 30.0) -> None:
        self._api_version = api_version
        self._token_env = token_env
        self._timeout_seconds = timeout_seconds

    def __call__(self, to: str, body: str) -> str:
        token = os.environ.get(self._token_env)
        if not token:
            raise ProtocolInvocationError(
                f"DiscordBotAPITransport requires the {self._token_env} environment variable -- this "
                f"is the documented ADAPTER READY / REQUIRES EXTERNAL CREDENTIALS boundary "
                f"(CONTRACT.md SS37); no token is configured in this environment"
            )

        import requests

        try:
            response = requests.post(
                f"https://discord.com/api/{self._api_version}/channels/{to}/messages",
                headers={"Authorization": f"Bot {token}"}, json={"content": body}, timeout=self._timeout_seconds,
            )
        except Exception as exc:
            raise ProtocolInvocationError(f"Discord Bot API request to channel {to!r} failed: {exc}") from exc

        if response.status_code >= 400:
            raise ProtocolInvocationError(
                f"Discord Bot API rejected the message to channel {to!r}: {response.status_code} {response.text[:500]}"
            )
        return str(response.json().get("id", ""))
