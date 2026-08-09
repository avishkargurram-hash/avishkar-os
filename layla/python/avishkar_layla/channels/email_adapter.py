"""EmailChannelAdapter -- a real avishkar_integration.ProtocolAdapter
implementation for email. See CONTRACT.md SS12.

STATUS: ADAPTER READY / REQUIRES EXTERNAL CREDENTIALS. The adapter
itself, its contract, and its tests are real and exercised end to end
against a fake transport (the same DI seam RESTAdapter already uses
instead of a live network call, Phase 4). Actually sending an email
requires a real transport function backed by SMTP/an email API and
real credentials -- neither is provided or faked here. See README.md
Deployment for what production activation requires.
"""

from __future__ import annotations

import time
from typing import Callable, Dict, Sequence, Tuple

from avishkar_integration import ProtocolInvocationError, ToolContract, ToolExecutionRequest, ToolExecutionResult
from avishkar_integration.protocol import ProtocolAdapter

# (to, subject, body) -> message_id. Raises ProtocolInvocationError on
# failure -- the same error type every ProtocolAdapter normalizes
# transport failures into (CONTRACT.md SS1 of mcp-factory).
EmailTransport = Callable[[str, str, str], str]


def _unconfigured_transport(to: str, subject: str, body: str) -> str:
    raise ProtocolInvocationError(
        "EmailChannelAdapter has no real transport configured -- this is the "
        "documented ADAPTER READY / REQUIRES EXTERNAL CREDENTIALS boundary "
        "(CONTRACT.md SS12): wire a real SMTP/email-API-backed transport "
        "before using this adapter in production."
    )


class EmailChannelAdapter(ProtocolAdapter):
    protocol_name = "email"

    def __init__(self, tools: Sequence[ToolContract] = (), *, transport: EmailTransport = _unconfigured_transport) -> None:
        self._tools: Dict[str, ToolContract] = {t.identity: t for t in tools}
        self._transport = transport

    def register_tool(self, contract: ToolContract) -> None:
        self._tools[contract.identity] = contract

    def discover_tools(self) -> Tuple[ToolContract, ...]:
        return tuple(self._tools.values())

    def invoke(self, contract: ToolContract, request: ToolExecutionRequest) -> ToolExecutionResult:
        payload = request.input or {}
        to = payload.get("to")
        subject = payload.get("subject", "")
        body = payload.get("body", "")
        if not to:
            raise ProtocolInvocationError("email tool call missing required 'to' field in input")

        start = time.monotonic()
        try:
            message_id = self._transport(to, subject, body)
        except ProtocolInvocationError:
            raise
        except Exception as exc:  # noqa: BLE001 -- normalized into our own hierarchy
            raise ProtocolInvocationError(f"email send to '{to}' failed: {exc}") from exc
        elapsed_ms = (time.monotonic() - start) * 1000

        return ToolExecutionResult(
            tool_identity=contract.identity, protocol=self.protocol_name, status="success",
            output={"message_id": message_id}, latency_ms=elapsed_ms,
        )
