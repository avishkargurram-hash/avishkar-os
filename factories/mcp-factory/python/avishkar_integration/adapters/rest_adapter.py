"""RESTAdapter -- a second, genuinely real ProtocolAdapter (stdlib
`urllib` only, zero third-party dependency) built specifically to prove
the Protocol Abstraction Layer is real, not an MCP-shaped wrapper with a
single implementation (ADR-0011 SS1).

REST tools are DECLARED (via `register_tool`), not discovered --
`protocol_config` on each ToolContract holds `{"method", "url",
"headers"}`. `transport` is the dependency-injection seam tests use
instead of a live network call.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple

from ..errors import ProtocolInvocationError
from ..protocol import ProtocolAdapter
from ..types import ToolContract, ToolExecutionRequest, ToolExecutionResult

Transport = Callable[[str, str, Mapping[str, str], Optional[bytes]], Tuple[int, bytes]]


def _default_transport(method: str, url: str, headers: Mapping[str, str], body: Optional[bytes]) -> Tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 -- url is caller-declared, not user input
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except urllib.error.URLError as exc:
        raise ProtocolInvocationError(f"REST request to '{url}' failed: {exc}") from exc


class RESTAdapter(ProtocolAdapter):
    protocol_name = "rest"

    def __init__(self, tools: Sequence[ToolContract] = (), *, transport: Transport = _default_transport) -> None:
        self._tools: Dict[str, ToolContract] = {t.identity: t for t in tools}
        self._transport = transport

    def register_tool(self, contract: ToolContract) -> None:
        """Declare a REST tool. Unlike MCP, REST has no discovery
        protocol -- every tool this adapter can call is declared here
        before the adapter is registered with a UniversalToolRegistry.
        """
        self._tools[contract.identity] = contract

    def discover_tools(self) -> Tuple[ToolContract, ...]:
        return tuple(self._tools.values())

    def invoke(self, contract: ToolContract, request: ToolExecutionRequest) -> ToolExecutionResult:
        config = contract.protocol_config
        method = str(config.get("method", "GET")).upper()
        url = config["url"]
        headers: Dict[str, str] = dict(config.get("headers", {}))
        body: Optional[bytes] = None

        if method in ("POST", "PUT", "PATCH") and request.input is not None:
            body = json.dumps(request.input).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        elif request.input:
            query = urllib.parse.urlencode(request.input)
            url = f"{url}?{query}" if query else url

        start = time.monotonic()
        try:
            status, raw = self._transport(method, url, headers, body)
        except ProtocolInvocationError:
            raise
        except Exception as exc:  # noqa: BLE001 -- normalized into our own hierarchy
            raise ProtocolInvocationError(f"REST request to '{url}' failed: {exc}") from exc
        elapsed_ms = (time.monotonic() - start) * 1000

        parsed: Any
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = raw.decode("utf-8", errors="replace")

        success = 200 <= status < 300
        return ToolExecutionResult(
            tool_identity=contract.identity,
            protocol=self.protocol_name,
            status="success" if success else "error",
            output=parsed if success else None,
            error=None if success else str(parsed),
            latency_ms=elapsed_ms,
            attempts=1,
        )
