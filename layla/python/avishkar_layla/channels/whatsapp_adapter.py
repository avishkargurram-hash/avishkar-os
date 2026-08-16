"""WhatsAppChannelAdapter -- a real avishkar_integration.ProtocolAdapter
implementation for WhatsApp. See CONTRACT.md SS12/SS27.

STATUS: ADAPTER READY / REQUIRES EXTERNAL CREDENTIALS -- the exact same
pattern `email_adapter.py` already established (Phase 16): the adapter,
its contract, and its tests are real and exercised end to end against a
fake transport (the same DI seam `RESTAdapter` uses instead of a live
network call). Actually sending a WhatsApp message requires a real
transport backed by a real WhatsApp Business API client and real
credentials -- neither is provided or faked here.

Mission Layla Part 9 (Channels): routing across multiple channels is
already solved by `avishkar_integration.UniversalToolRegistry`
(Phase 4, locked) -- register this adapter (and `EmailChannelAdapter`,
and any future channel adapter) with one registry; the registry is the
router. Building a second, competing router here would duplicate MCP,
which this mission explicitly forbids.
"""

from __future__ import annotations

import time
from typing import Callable, Dict, Sequence, Tuple

from avishkar_integration import ProtocolInvocationError, ToolContract, ToolExecutionRequest, ToolExecutionResult
from avishkar_integration.protocol import ProtocolAdapter

# (to, body) -> message_id. Raises ProtocolInvocationError on failure.
WhatsAppTransport = Callable[[str, str], str]


def _unconfigured_transport(to: str, body: str) -> str:
    raise ProtocolInvocationError(
        "WhatsAppChannelAdapter has no real transport configured -- this is the "
        "documented ADAPTER READY / REQUIRES EXTERNAL CREDENTIALS boundary "
        "(CONTRACT.md SS12/SS27): wire a real WhatsApp Business API-backed "
        "transport before using this adapter in production."
    )


class WhatsAppChannelAdapter(ProtocolAdapter):
    protocol_name = "whatsapp"

    def __init__(self, tools: Sequence[ToolContract] = (), *, transport: WhatsAppTransport = _unconfigured_transport) -> None:
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
            raise ProtocolInvocationError("whatsapp tool call missing required 'to' field in input")

        start = time.monotonic()
        try:
            message_id = self._transport(to, body)
        except ProtocolInvocationError:
            raise
        except Exception as exc:  # noqa: BLE001 -- normalized into our own hierarchy
            raise ProtocolInvocationError(f"whatsapp send to '{to}' failed: {exc}") from exc
        elapsed_ms = (time.monotonic() - start) * 1000

        return ToolExecutionResult(
            tool_identity=contract.identity, protocol=self.protocol_name, status="success",
            output={"message_id": message_id}, latency_ms=elapsed_ms,
        )
