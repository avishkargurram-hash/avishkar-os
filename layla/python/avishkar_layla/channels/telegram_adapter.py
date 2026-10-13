"""TelegramChannelAdapter -- a real avishkar_integration.ProtocolAdapter
implementation for Telegram. See CONTRACT.md SS37.

STATUS: ADAPTER READY / REQUIRES EXTERNAL CREDENTIALS -- same pattern
as email_adapter.py/whatsapp_adapter.py. `TelegramBotAPITransport` is a
REAL HTTP client against Telegram's real Bot API; no bot token is
configured in this environment, so live delivery is untested here (a
real network call with a deliberately invalid token, proving the
transport genuinely reaches api.telegram.org and parses a real error
response, IS exercised in test_telegram_bot_api_transport.py).
"""

from __future__ import annotations

import os
import time
from typing import Callable, Dict, Sequence, Tuple

from avishkar_integration import ProtocolInvocationError, ToolContract, ToolExecutionRequest, ToolExecutionResult
from avishkar_integration.protocol import ProtocolAdapter

# (to, body) -> message_id. `to` is a Telegram chat_id (string form).
TelegramTransport = Callable[[str, str], str]


def _unconfigured_transport(to: str, body: str) -> str:
    raise ProtocolInvocationError(
        "TelegramChannelAdapter has no real transport configured -- this is the documented "
        "ADAPTER READY / REQUIRES EXTERNAL CREDENTIALS boundary (CONTRACT.md SS37): wire a real "
        "Telegram Bot API-backed transport before using this adapter in production."
    )


class TelegramChannelAdapter(ProtocolAdapter):
    protocol_name = "telegram"

    def __init__(self, tools: Sequence[ToolContract] = (), *, transport: TelegramTransport = _unconfigured_transport) -> None:
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
            raise ProtocolInvocationError("telegram tool call missing required 'to' field in input")

        start = time.monotonic()
        try:
            message_id = self._transport(to, body)
        except ProtocolInvocationError:
            raise
        except Exception as exc:  # noqa: BLE001 -- normalized into our own hierarchy
            raise ProtocolInvocationError(f"telegram send to '{to}' failed: {exc}") from exc
        elapsed_ms = (time.monotonic() - start) * 1000

        return ToolExecutionResult(
            tool_identity=contract.identity, protocol=self.protocol_name, status="success",
            output={"message_id": message_id}, latency_ms=elapsed_ms,
        )


class TelegramBotAPITransport:
    """REAL HTTP client for Telegram's real Bot API
    (`POST https://api.telegram.org/bot<token>/sendMessage`).
    """

    def __init__(self, *, token_env: str = "TELEGRAM_BOT_TOKEN", timeout_seconds: float = 30.0) -> None:
        self._token_env = token_env
        self._timeout_seconds = timeout_seconds

    def __call__(self, to: str, body: str) -> str:
        token = os.environ.get(self._token_env)
        if not token:
            raise ProtocolInvocationError(
                f"TelegramBotAPITransport requires the {self._token_env} environment variable -- this "
                f"is the documented ADAPTER READY / REQUIRES EXTERNAL CREDENTIALS boundary "
                f"(CONTRACT.md SS37); no token is configured in this environment"
            )

        import requests

        try:
            response = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": to, "text": body}, timeout=self._timeout_seconds,
            )
        except Exception as exc:
            raise ProtocolInvocationError(f"Telegram Bot API request to {to!r} failed: {exc}") from exc

        payload = response.json()
        if not payload.get("ok"):
            raise ProtocolInvocationError(
                f"Telegram Bot API rejected the message to {to!r}: {response.status_code} {payload}"
            )
        return str(payload["result"]["message_id"])
