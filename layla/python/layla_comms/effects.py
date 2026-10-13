"""The ONLY place side effects happen. Everything the pipeline can do to
the outside world is a method here, and each method checks, in order:
kill switch -> shadow/live flag -> audit -> act.

Deliberately absent: any send/reply/forward method. The Gmail transport
protocol (GmailPort) does not expose one either, so "never auto-send" is
enforced by capability omission, not by a flag someone could flip.
"""

from __future__ import annotations

from typing import Optional, Protocol

from .store import Store


class GmailPort(Protocol):
    def add_label(self, msg_id: str, label_name: str) -> None: ...
    def archive(self, msg_id: str) -> None: ...
    def create_draft(self, thread_id: str, to_email: str, subject: str, body: str,
                     in_reply_to: str, references: str) -> str: ...


class NotifyPort(Protocol):
    def send(self, text: str) -> None: ...


class Effects:
    def __init__(self, store: Store, gmail: GmailPort, notifier: NotifyPort):
        self._s = store
        self._g = gmail
        self._n = notifier

    def _gate(self, action: str, detail: dict) -> bool:
        """True only when the action should really execute."""
        if self._s.killed():
            self._s.audit("blocked_kill", {"action": action, **detail})
            return False
        if not self._s.action_live(action):
            self._s.audit("shadow", {"action": action, **detail})
            return False
        self._s.audit("live", {"action": action, **detail})
        return True

    def label(self, msg_id: str, label_name: str) -> bool:
        if self._gate("label", {"msg_id": msg_id, "label": label_name}):
            self._g.add_label(msg_id, label_name)
            return True
        return False

    def archive(self, msg_id: str) -> bool:
        if self._gate("archive", {"msg_id": msg_id}):
            self._g.archive(msg_id)
            return True
        return False

    def draft(self, msg_id: str, thread_id: str, to_email: str, subject: str, body: str,
              in_reply_to: str = "", references: str = "") -> Optional[str]:
        """Creates a Gmail DRAFT only. Recorded in the queue either way so
        shadow mode shows what would have been drafted."""
        live = self._gate("draft", {"msg_id": msg_id, "to": to_email})
        gid = ""
        status = "shadow"
        if live:
            gid = self._g.create_draft(thread_id, to_email, subject, body, in_reply_to, references)
            status = "drafted"
        self._s.add_draft(msg_id, thread_id, to_email, subject, body, gid, status)
        return gid or None

    def notify(self, text: str) -> bool:
        # Notifying the owner is always allowed, even when killed or in
        # shadow: it is the owner's own channel and the safety net.
        try:
            self._n.send(text)
            self._s.audit("notify", {"len": len(text)})
            return True
        except Exception as e:  # never let a notify failure break triage
            self._s.audit("notify_failed", {"error": str(e)[:200]})
            return False
