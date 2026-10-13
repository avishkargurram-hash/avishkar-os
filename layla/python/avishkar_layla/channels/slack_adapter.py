"""SlackChannelAdapter -- a real avishkar_integration.ProtocolAdapter
implementation for Slack. See CONTRACT.md SS37.

STATUS: ADAPTER READY / REQUIRES EXTERNAL CREDENTIALS -- same pattern
as email_adapter.py/whatsapp_adapter.py/telegram_adapter.py.
`SlackWebAPITransport` is a REAL HTTP client against Slack's real Web
API; no bot token is configured in this environment.
"""

from __future__ import annotations

import os
import time
from typing import Callable, Dict, Sequence, Tuple

from avishkar_integration import ProtocolInvocationError, ToolContract, ToolExecutionRequest, ToolExecutionResult
from avishkar_integration.protocol import ProtocolAdapter

# (to, body) -> message_id ("ts", Slack's message timestamp/id). `to` is
# a Slack channel ID or name.
SlackTransport = Callable[[str, str], str]


def _unconfigured_transport(to: str, body: str) -> str:
    raise ProtocolInvocationError(
        "SlackChannelAdapter has no real transport configured -- this is the documented "
        "ADAPTER READY / REQUIRES EXTERNAL CREDENTIALS boundary (CONTRACT.md SS37): wire a real "
        "Slack Web API-backed transport before using this adapter in production."
    )


class SlackChannelAdapter(ProtocolAdapter):
    protocol_name = "slack"

    def __init__(self, tools: Sequence[ToolContract] = (), *, transport: SlackTransport = _unconfigured_transport) -> None:
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
            raise ProtocolInvocationError("slack tool call missing required 'to' field in input")

        start = time.monotonic()
        try:
            message_id = self._transport(to, body)
        except ProtocolInvocationError:
            raise
        except Exception as exc:  # noqa: BLE001 -- normalized into our own hierarchy
            raise ProtocolInvocationError(f"slack send to '{to}' failed: {exc}") from exc
        elapsed_ms = (time.monotonic() - start) * 1000

        return ToolExecutionResult(
            tool_identity=contract.identity, protocol=self.protocol_name, status="success",
            output={"message_id": message_id}, latency_ms=elapsed_ms,
        )


class SlackWebAPITransport:
    """REAL HTTP client for Slack's real Web API
    (`POST https://slack.com/api/chat.postMessage`). Slack's API
    always returns HTTP 200 even on failure -- the real `ok` field in
    the JSON body is what determines success, not the status code, so
    this transport checks that field rather than `response.raise_for_status()`.
    """

    def __init__(self, *, token_env: str = "SLACK_BOT_TOKEN", timeout_seconds: float = 30.0) -> None:
        self._token_env = token_env
        self._timeout_seconds = timeout_seconds

    def __call__(self, to: str, body: str) -> str:
        token = os.environ.get(self._token_env)
        if not token:
            raise ProtocolInvocationError(
                f"SlackWebAPITransport requires the {self._token_env} environment variable -- this "
                f"is the documented ADAPTER READY / REQUIRES EXTERNAL CREDENTIALS boundary "
                f"(CONTRACT.md SS37); no token is configured in this environment"
            )

        import requests

        try:
            response = requests.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {token}"},
                json={"channel": to, "text": body}, timeout=self._timeout_seconds,
            )
        except Exception as exc:
            raise ProtocolInvocationError(f"Slack Web API request to {to!r} failed: {exc}") from exc

        payload = response.json()
        if not payload.get("ok"):
            raise ProtocolInvocationError(
                f"Slack Web API rejected the message to {to!r}: {response.status_code} {payload}"
            )
        return str(payload.get("ts", ""))
