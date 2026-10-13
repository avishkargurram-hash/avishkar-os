"""Real SSRF guard -- Mission Layla Directive D, Part XIII (Security
Hardening). See CONTRACT.md SS52.

A genuine security finding from this security-hardening pass's own
review of the existing code, not a theoretical concern: `EMBODIMENT_BROWSER`
is LOW-risk-by-default for any text that doesn't match `classify_risk()`'s
dangerous-pattern list (a real, documented, deliberate finding from
ADR-0030) -- but "navigate to a URL" is not itself dangerous-sounding
TEXT even when the URL is `http://169.254.169.254/latest/meta-data/iam/
security-credentials/` (the real AWS/GCP/Azure link-local cloud-
metadata endpoint). If this process ever runs on a real cloud VM with
an attached IAM role, a `navigate` call to that address -- reachable
with NO approval gate at all under the prior code, since nothing about
that request read as "dangerous" -- could exfiltrate real, live cloud
credentials to whatever the browsing plan does with the resulting page
content. `unsafe_navigation_reason()` closes this: a real, hard block
(not merely a risk-classification nudge) inside `BrowserExecutor`
itself, refusing navigation to a private/loopback/link-local/reserved
address or a known metadata hostname BEFORE Playwright ever opens a
real connection -- there is essentially no legitimate reason for
Layla's own web browsing to target these.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Optional
from urllib.parse import urlparse

_BLOCKED_HOSTNAMES = frozenset({
    "metadata.google.internal",
    "metadata",
})


def unsafe_navigation_reason(url: str) -> Optional[str]:
    """A real SSRF check. Returns a human-readable reason string if
    `url` targets a private/internal/metadata address (unsafe to
    navigate to), or `None` if it's safe to proceed. Never raises for
    a malformed or unresolvable URL -- that's a normal navigation
    failure for the real browser itself to report, not this guard's
    job to pre-empt.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https"):
        return None  # data:/about:/etc. -- never reaches a real network host
    host = parsed.hostname
    if not host:
        return None
    if host.lower() in _BLOCKED_HOSTNAMES:
        return f"{host!r} is a known cloud-metadata hostname"

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        try:
            ip = ipaddress.ip_address(socket.gethostbyname(host))
        except (socket.gaierror, OSError, ValueError):
            return None  # can't resolve -- let the real navigation attempt fail naturally

    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast:
        return f"{host!r} resolves to a private/internal address ({ip}) -- refusing to navigate there"
    return None
