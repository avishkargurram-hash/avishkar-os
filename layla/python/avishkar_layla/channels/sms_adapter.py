"""SMSChannelAdapter -- a real avishkar_integration.ProtocolAdapter
implementation for SMS. See CONTRACT.md SS37.

STATUS: ADAPTER READY / REQUIRES EXTERNAL CREDENTIALS -- same pattern
as the other channel adapters. `TwilioSMSTransport` is a REAL client
using the real, installed `twilio` SDK; no Twilio account is
configured in this environment.
"""

from __future__ import annotations

import os
import time
from typing import Callable, Dict, Sequence, Tuple

from avishkar_integration import ProtocolInvocationError, ToolContract, ToolExecutionRequest, ToolExecutionResult
from avishkar_integration.protocol import ProtocolAdapter

# (to, body) -> message_sid.
SMSTransport = Callable[[str, str], str]


def _unconfigured_transport(to: str, body: str) -> str:
    raise ProtocolInvocationError(
        "SMSChannelAdapter has no real transport configured -- this is the documented "
        "ADAPTER READY / REQUIRES EXTERNAL CREDENTIALS boundary (CONTRACT.md SS37): wire a real "
        "Twilio-backed transport before using this adapter in production."
    )


class SMSChannelAdapter(ProtocolAdapter):
    protocol_name = "sms"

    def __init__(self, tools: Sequence[ToolContract] = (), *, transport: SMSTransport = _unconfigured_transport) -> None:
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
            raise ProtocolInvocationError("sms tool call missing required 'to' field in input")

        start = time.monotonic()
        try:
            message_id = self._transport(to, body)
        except ProtocolInvocationError:
            raise
        except Exception as exc:  # noqa: BLE001 -- normalized into our own hierarchy
            raise ProtocolInvocationError(f"sms send to '{to}' failed: {exc}") from exc
        elapsed_ms = (time.monotonic() - start) * 1000

        return ToolExecutionResult(
            tool_identity=contract.identity, protocol=self.protocol_name, status="success",
            output={"message_id": message_id}, latency_ms=elapsed_ms,
        )


class TwilioSMSTransport:
    """REAL client using the real, installed `twilio` SDK
    (`twilio.rest.Client`). Credentials read from environment
    variables at call time (never hardcoded).
    """

    def __init__(
        self, *, from_number: str, account_sid_env: str = "TWILIO_ACCOUNT_SID",
        auth_token_env: str = "TWILIO_AUTH_TOKEN", timeout_seconds: float = 30.0,
    ) -> None:
        self._from_number = from_number
        self._account_sid_env = account_sid_env
        self._auth_token_env = auth_token_env
        self._timeout_seconds = timeout_seconds

    def __call__(self, to: str, body: str) -> str:
        account_sid = os.environ.get(self._account_sid_env)
        auth_token = os.environ.get(self._auth_token_env)
        if not account_sid or not auth_token:
            raise ProtocolInvocationError(
                f"TwilioSMSTransport requires the {self._account_sid_env}/{self._auth_token_env} "
                f"environment variables -- this is the documented ADAPTER READY / REQUIRES EXTERNAL "
                f"CREDENTIALS boundary (CONTRACT.md SS37); no credential is configured in this environment"
            )

        try:
            from twilio.rest import Client
        except ImportError as exc:
            raise ProtocolInvocationError("the 'twilio' package is not installed -- required for TwilioSMSTransport") from exc

        try:
            client = Client(account_sid, auth_token)
            message = client.messages.create(to=to, from_=self._from_number, body=body)
        except ProtocolInvocationError:
            raise
        except Exception as exc:
            raise ProtocolInvocationError(f"Twilio SMS send to {to!r} failed: {exc}") from exc

        return message.sid
