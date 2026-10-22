"""The pipeline: clean -> classify -> decide -> (draft) -> effects.

Fail-closed: any exception on a message leaves it untouched in Gmail and
records an audit entry; the next poll may retry it (it is not marked
processed), and the owner is never sent an error text on a contact's behalf.
"""

from __future__ import annotations

from typing import Dict

from . import firewall, policy
from .effects import Effects
from .llm import Model
from .store import Store
from .types import TIER_APPROVE, InboundMessage


class Triage:
    def __init__(self, store: Store, model: Model, effects: Effects, owner_email: str = ""):
        self.store = store
        self.model = model
        self.fx = effects
        self.owner = owner_email.strip().lower()

    def process(self, msg: InboundMessage) -> Dict[str, object]:
        if self.store.seen(msg.msg_id):
            return {"skipped": "already processed"}
        if self.store.killed():
            self.store.audit("blocked_kill", {"action": "process", "msg_id": msg.msg_id})
            return {"skipped": "kill switch"}
        try:
            return self._process(msg)
        except Exception as e:
            self.store.audit("error", {"msg_id": msg.msg_id, "error": str(e)[:200]})
            return {"error": str(e)[:200]}

    def _process(self, msg: InboundMessage) -> Dict[str, object]:
        clean = firewall.clean(msg)
        contact = self.store.get_contact(clean.sender_email)
        if self.owner and clean.sender_email == self.owner:
            return self._finish(msg, clean, None, "own message", skip=True)

        cls = self.model.classify(clean)
        dec = policy.decide(msg, cls, contact, clean.injection_hits)
        self.store.audit("decision", {
            "msg_id": msg.msg_id, "category": cls.category, "conf": cls.confidence,
            "label": dec.label, "archive": dec.archive, "draft": dec.draft,
            "tier": dec.tier, "reasons": list(dec.reasons)})

        if dec.label:
            self.fx.label(msg.msg_id, dec.label)

        if dec.draft and contact.policy != "never_touch":
            self._try_draft(msg, clean, contact)

        if dec.archive:
            self.fx.archive(msg.msg_id)

        self.store.record_processed(msg.msg_id, cls.category, cls.summary,
                                    clean.sender_email, clean.subject, dec.notify, dec.tier)
        if dec.notify == "now":
            self.fx.notify(f"{'URGENT' if cls.category == 'urgent' else 'Needs reply'} from "
                           f"{clean.sender_name or clean.sender_email}: {clean.subject}\n{cls.summary}")
        return {"category": cls.category, "archive": dec.archive, "draft": dec.draft,
                "tier": dec.tier, "reasons": list(dec.reasons)}

    def _finish(self, msg, clean, cls, why, skip=False):
        self.store.record_processed(msg.msg_id, "own", why, clean.sender_email, clean.subject, None, 0)
        return {"skipped": why}

    def _try_draft(self, msg: InboundMessage, clean, contact) -> None:
        body = self.model.draft(clean, contact)
        if not body:
            self.store.audit("draft_none", {"msg_id": msg.msg_id})
            return
        flags = policy.check_draft(body, clean.sender_email)
        if flags:
            # Do not create the draft; the owner handles it personally.
            self.store.audit("draft_blocked", {"msg_id": msg.msg_id, "flags": flags})
            self.fx.notify(f"Needs your personal reply (draft withheld: {', '.join(flags)}): "
                           f"{clean.subject} from {clean.sender_email}")
            return
        subject = clean.subject if clean.subject.lower().startswith("re:") else f"Re: {clean.subject}"
        self.fx.draft(msg.msg_id, msg.thread_id, clean.sender_email, subject, body,
                      in_reply_to=msg.message_id_header,
                      references=(msg.references + " " + msg.message_id_header).strip())
