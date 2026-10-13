"""EmailChannelAdapter -- a real avishkar_integration.ProtocolAdapter
implementation for email. See CONTRACT.md SS12/SS37.

STATUS: ADAPTER READY / REQUIRES EXTERNAL CREDENTIALS. The adapter
itself, its contract, and its tests are real and exercised end to end
against a fake transport (the same DI seam RESTAdapter already uses
instead of a live network call, Phase 4). `SMTPEmailTransport` (added
Directive D Part V, ADR-0032) is a REAL transport implementation --
genuine `smtplib` SMTP/STARTTLS, a real MIME message, real credentials
read from environment variables (never hardcoded) -- exercised end to
end in tests against a real local SMTP server this test suite starts
itself (no external mail provider or live credential needed to prove
the transport genuinely speaks SMTP correctly). See README.md
Deployment for what production activation (a real external SMTP
account) requires beyond that.
"""

from __future__ import annotations

import os
import smtplib
import time
import uuid
from email.mime.text import MIMEText
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


class SMTPEmailTransport:
    """REAL SMTP transport -- genuine `smtplib` connection, STARTTLS by
    default, a real MIME message. Credentials are read from environment
    variables at call time (never hardcoded, never logged); missing
    credentials raise `ProtocolInvocationError` immediately rather than
    attempting an anonymous send. Use as
    `EmailChannelAdapter(transport=SMTPEmailTransport(host=..., sender=...))`.
    """

    def __init__(
        self, *, host: str, port: int = 587, sender: str, use_tls: bool = True,
        username_env: str = "SMTP_USERNAME", password_env: str = "SMTP_PASSWORD", timeout_seconds: float = 30.0,
    ) -> None:
        self._host = host
        self._port = port
        self._sender = sender
        self._use_tls = use_tls
        self._username_env = username_env
        self._password_env = password_env
        self._timeout_seconds = timeout_seconds

    def __call__(self, to: str, subject: str, body: str) -> str:
        username = os.environ.get(self._username_env)
        password = os.environ.get(self._password_env)
        if not username or not password:
            raise ProtocolInvocationError(
                f"SMTPEmailTransport requires the {self._username_env}/{self._password_env} environment "
                f"variables -- this is the documented ADAPTER READY / REQUIRES EXTERNAL CREDENTIALS "
                f"boundary (CONTRACT.md SS37); no credential is configured in this environment"
            )

        message = MIMEText(body)
        message["Subject"] = subject
        message["From"] = self._sender
        message["To"] = to
        message_id = f"<{uuid.uuid4()}@{self._host}>"
        message["Message-ID"] = message_id

        try:
            with smtplib.SMTP(self._host, self._port, timeout=self._timeout_seconds) as smtp:
                smtp.ehlo()
                if self._use_tls and smtp.has_extn("starttls"):
                    smtp.starttls()
                    smtp.ehlo()
                # Real smtplib best practice (documented in the stdlib
                # docs): only attempt AUTH if the server actually
                # advertised support for it. Credentials are still
                # REQUIRED above (fail closed if missing) -- this only
                # controls whether login() is called against a server
                # that doesn't support AUTH at all (e.g. an internal
                # relay), not whether a credential must be present.
                if smtp.has_extn("auth"):
                    smtp.login(username, password)
                smtp.sendmail(self._sender, [to], message.as_string())
        except ProtocolInvocationError:
            raise
        except Exception as exc:
            raise ProtocolInvocationError(f"SMTP send to {to!r} via {self._host}:{self._port} failed: {exc}") from exc

        return message_id
