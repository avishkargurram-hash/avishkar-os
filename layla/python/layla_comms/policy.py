"""Approval matrix as code. Pure functions, no I/O, fully deterministic.

The model proposes (a Classification); this module decides. Nothing here
trusts the model's word on its own: automatic archiving needs an
independent structural signal from the message headers, and any
injection flag turns automation off for that message.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from .types import (
    NOISE_CATEGORIES, TIER_APPROVE, TIER_NEVER, TIER_SILENT,
    Classification, Contact, Decision, InboundMessage,
)

ARCHIVE_MIN_CONFIDENCE = 0.85

LABELS = {
    "urgent": "Layla/Urgent",
    "needs_reply": "Layla/NeedsReply",
    "fyi": "Layla/FYI",
    "newsletter": "Layla/Noise",
    "promo": "Layla/Noise",
    "notification": "Layla/Noise",
    "spam_suspect": "Layla/SpamSuspect",
    "needs_human": "Layla/NeedsYou",
}

_MONEY = re.compile(
    r"(?:₹|\brs\.?|\binr\b|\$|\busd\b|€|£|\beur\b)\s?\d|\b\d[\d,.]*\s?(?:lakh|lakhs|crore|thousand|million|k\b"
    r"|rupees?|rupaye|rupayi|dollars?|bucks|usd|inr)|\b(?:upi|gpay|google\s?pay|phonepe|paytm|payment|advance|invoice)\b",
    re.I,
)
_TIME = re.compile(
    r"\b\d{1,2}(?::\d{2})?\s?(?:am|pm)\b|\b(?:mon|tues?|wednes|thurs?|fri|satur|sun)day\b"
    r"|\b(?:tomorrow|tonight|next\s+week|eod|deadline)\b|\bby\s+(?:the\s+)?(?:end|monday|tuesday|wednesday|thursday|friday)\b"
    r"|\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}\b",
    re.I,
)
_PROMISE = re.compile(
    r"\b(?:i|we)(?:\s+will|'ll|\s+promise|\s+guarantee|\s+confirm|\s+agree|\s+accept)\b.{0,25}?"
    r"\b(?:send|attend|be\s+there|join|pay|transfer|call|meet|come|do|share|finish|deliver|sign|approve|confirm|agree|accept|promise|guarantee)\b"
    r"|\bcount\s+me\s+in\b|\bit'?s\s+a\s+deal\b|\bi'?m\s+in\b|\bapproved\b|\bi\s+agree\b|\byes,?\s+(?:i|we)\s+can\b|\bconfirmed\b",
    re.I,
)
_LEGAL = re.compile(r"\b(?:contract|agreement|nda|liabilit\w+|lawsuit|indemnif\w+|legally)\b", re.I)
_PERSONAL = re.compile(
    r"\botp\b|\bpassword\b|\bpasscode\b|\bpin\s+(?:is|number)\b|\b\d{4}[ -]?\d{4}[ -]?\d{4}\b"
    r"|\baccount\s+(?:no|number)\b|\bifsc\b|\bpan\s+(?:no|number|card)\b|\baadhaar\b",
    re.I,
)
_URL = re.compile(r"https?://|www\.", re.I)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\d\s-]{8,}\d)(?!\d)")

_CHECKS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("money", _MONEY), ("time_or_date", _TIME), ("promise", _PROMISE),
    ("legal", _LEGAL), ("personal_data", _PERSONAL), ("link", _URL),
    ("email_address", _EMAIL), ("phone_number", _PHONE),
)


def commitment_flags(text: str) -> List[str]:
    """Deterministic scan of OUTBOUND text. A non-empty result means the
    text may commit the owner to something (or carry a payload) and must
    not be auto-created as a draft."""
    text = text.replace("’", "'").replace("‘", "'")
    return [name for name, rx in _CHECKS if rx.search(text)]


def has_bulk_signal(msg: InboundMessage) -> bool:
    """Independent, header-level evidence that a message is machine mail.
    The model alone is never enough to archive something."""
    h = {k.lower(): v for k, v in msg.headers.items()}
    if "list-unsubscribe" in h or "list-id" in h:
        return True
    if h.get("precedence", "").lower() in ("bulk", "list", "junk"):
        return True
    if h.get("auto-submitted", "no").lower() != "no":
        return True
    local = msg.sender_email.split("@")[0].lower()
    return bool(re.match(r"^(?:no-?reply|do-?not-?reply|notifications?|mailer|alerts?|news(?:letter)?)\b", local))


def decide(msg: InboundMessage, cls: Classification, contact: Contact,
           injection_hits: Tuple[str, ...]) -> Decision:
    reasons: List[str] = []

    if contact.policy == "never_touch":
        return Decision(None, False, False, "digest", TIER_SILENT, ("contact is never_touch",))

    if injection_hits or cls.injection_suspected:
        flag = ",".join(injection_hits) or "model-flagged"
        return Decision(LABELS["needs_human"], False, False, "digest", TIER_NEVER,
                        (f"injection suspected ({flag}); automation disabled",))

    if cls.category == "needs_human":
        return Decision(LABELS["needs_human"], False, False, "digest", TIER_NEVER,
                        (cls.reason or "classifier could not decide",))

    label = LABELS[cls.category]
    archive = False
    draft = False
    notify = "digest"
    tier = TIER_SILENT

    if cls.category in NOISE_CATEGORIES:
        if contact.policy == "vip":
            reasons.append("vip sender: never archived")
        elif cls.confidence < ARCHIVE_MIN_CONFIDENCE:
            reasons.append(f"confidence {cls.confidence:.2f} < {ARCHIVE_MIN_CONFIDENCE}: not archived")
        elif not has_bulk_signal(msg):
            reasons.append("no bulk/list header signal: not archived")
        else:
            archive = True
    elif cls.category in ("urgent", "needs_reply"):
        tier = TIER_APPROVE
        if re.search(r"(?:^|[^a-z])(?:no-?reply|do-?not-?reply)(?:[^a-z]|$)", msg.sender_email.lower()):
            reasons.append("sender is a no-reply address: no draft")
        elif has_bulk_signal(msg):
            reasons.append("bulk/automated sender: no draft")
        else:
            draft = True
        if cls.category == "urgent":
            notify = "now"

    if contact.policy == "vip" and cls.category in ("urgent", "needs_reply"):
        notify = "now"

    return Decision(label, archive, draft, notify, tier, tuple(reasons))


def check_draft(body: str, recipient_email: str) -> List[str]:
    """Flags for a model-written draft. The recipient's own address is
    permitted; any other address, link, number or commitment is not."""
    scrubbed = body.replace(recipient_email, "") if recipient_email else body
    return commitment_flags(scrubbed)
