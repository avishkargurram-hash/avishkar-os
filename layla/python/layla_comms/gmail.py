"""Gmail REST client (stdlib only). Exposes read, label, archive and
create-draft. There is intentionally NO send, reply or forward method.

The OAuth scope gmail.modify technically allows sending, so the guarantee
is this class's surface plus Effects/GmailPort, not Google's scope.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from email import message_from_bytes, policy as email_policy
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Any, Dict, List, Optional, Tuple

from .types import InboundMessage

API = "https://gmail.googleapis.com/gmail/v1/users/me"
TOKEN_URL = "https://oauth2.googleapis.com/token"
KEEP_HEADERS = ("list-unsubscribe", "list-id", "precedence", "auto-submitted")


class GmailError(RuntimeError):
    pass


class GmailClient:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str,
                 http=None, clock=time.time):
        self._cid, self._secret, self._rt = client_id, client_secret, refresh_token
        self._http = http or self._urlopen
        self._clock = clock
        self._token = ""
        self._exp = 0.0
        self._labels: Dict[str, str] = {}

    @staticmethod
    def _urlopen(method: str, url: str, headers: dict, body: Optional[bytes]) -> Tuple[int, bytes]:
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def _access_token(self) -> str:
        if self._token and self._clock() < self._exp - 60:
            return self._token
        form = urllib.parse.urlencode({
            "client_id": self._cid, "client_secret": self._secret,
            "refresh_token": self._rt, "grant_type": "refresh_token"}).encode()
        st, raw = self._http("POST", TOKEN_URL,
                             {"Content-Type": "application/x-www-form-urlencoded"}, form)
        if st != 200:
            raise GmailError(f"token refresh failed ({st}); re-run oauth_setup")
        d = json.loads(raw)
        self._token = d["access_token"]
        self._exp = self._clock() + int(d.get("expires_in", 3600))
        return self._token

    def _call(self, method: str, path: str, payload: Optional[dict] = None) -> Any:
        h = {"Authorization": f"Bearer {self._access_token()}"}
        body = None
        if payload is not None:
            body = json.dumps(payload).encode()
            h["Content-Type"] = "application/json"
        st, raw = self._http(method, API + path, h, body)
        if st >= 400:
            raise GmailError(f"{method} {path} -> {st}: {raw[:200]!r}")
        return json.loads(raw) if raw else {}

    # ---- labels ----------------------------------------------------------
    def _label_id(self, name: str) -> str:
        if not self._labels:
            for lb in self._call("GET", "/labels").get("labels", []):
                self._labels[lb["name"]] = lb["id"]
        if name not in self._labels:
            lb = self._call("POST", "/labels", {
                "name": name, "labelListVisibility": "labelShow",
                "messageListVisibility": "show"})
            self._labels[name] = lb["id"]
        return self._labels[name]

    def add_label(self, msg_id: str, label_name: str) -> None:
        self._call("POST", f"/messages/{msg_id}/modify", {"addLabelIds": [self._label_id(label_name)]})

    def archive(self, msg_id: str) -> None:
        self._call("POST", f"/messages/{msg_id}/modify", {"removeLabelIds": ["INBOX"]})

    # ---- drafts (never send) --------------------------------------------
    def create_draft(self, thread_id: str, to_email: str, subject: str, body: str,
                     in_reply_to: str = "", references: str = "") -> str:
        m = EmailMessage()
        m["To"] = to_email
        m["Subject"] = subject
        if in_reply_to:
            m["In-Reply-To"] = in_reply_to
        if references:
            m["References"] = references
        m.set_content(body)
        raw = base64.urlsafe_b64encode(m.as_bytes()).decode()
        d = self._call("POST", "/drafts", {"message": {"raw": raw, "threadId": thread_id}})
        return d["id"]

    # ---- reading ---------------------------------------------------------
    def list_recent(self, query: str = "in:inbox newer_than:2d", limit: int = 25) -> List[str]:
        q = urllib.parse.quote(query)
        d = self._call("GET", f"/messages?q={q}&maxResults={limit}")
        return [m["id"] for m in d.get("messages", [])]

    def fetch(self, msg_id: str) -> InboundMessage:
        d = self._call("GET", f"/messages/{msg_id}?format=raw")
        raw = base64.urlsafe_b64decode(d["raw"] + "=" * (-len(d["raw"]) % 4))
        return parse_raw(raw, msg_id, d.get("threadId", msg_id),
                         float(d.get("internalDate", 0)) / 1000.0)


def parse_raw(raw: bytes, msg_id: str, thread_id: str, received_at: float) -> InboundMessage:
    m = message_from_bytes(raw, policy=email_policy.default)
    name, addr = parseaddr(str(m.get("From", "")))
    plain, html = "", ""
    for part in m.walk():
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        ctype = part.get_content_type()
        try:
            text = part.get_content()
        except Exception:
            continue
        if ctype == "text/plain" and not plain:
            plain = text
        elif ctype == "text/html" and not html:
            html = text
    headers = {k: str(m.get(k, "")) for k in KEEP_HEADERS if m.get(k) is not None}
    return InboundMessage(
        channel="gmail", msg_id=msg_id, thread_id=thread_id,
        sender_email=addr.lower(), sender_name=name,
        subject=str(m.get("Subject", "")), body_plain=plain, body_html=html,
        received_at=received_at, message_id_header=str(m.get("Message-ID", "")),
        references=str(m.get("References", "")), headers=headers)
