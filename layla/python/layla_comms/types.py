"""Plain data types shared across layla_comms. No behavior, no I/O."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

CATEGORIES: Tuple[str, ...] = (
    "urgent", "needs_reply", "fyi", "newsletter", "promo",
    "notification", "spam_suspect", "needs_human",
)
NOISE_CATEGORIES = ("newsletter", "promo", "notification")

# Contact policies. "default" is what an unknown sender gets.
POLICIES: Tuple[str, ...] = ("default", "vip", "draft_only", "never_touch")

# Actions that can be switched from shadow to live, one at a time.
ACTIONS: Tuple[str, ...] = ("label", "archive", "draft")

TIER_SILENT, TIER_DELAYED, TIER_APPROVE, TIER_NEVER = 0, 1, 2, 3


@dataclass(frozen=True)
class InboundMessage:
    channel: str
    msg_id: str
    thread_id: str
    sender_email: str
    sender_name: str
    subject: str
    body_plain: str
    body_html: str
    received_at: float
    message_id_header: str = ""
    references: str = ""
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CleanMessage:
    """What the model is allowed to see: sanitised, capped, fenced."""
    msg_id: str
    sender_email: str
    sender_name: str
    subject: str
    body: str
    injection_hits: Tuple[str, ...]


@dataclass(frozen=True)
class Classification:
    category: str
    confidence: float
    summary: str
    needs_reply: bool
    injection_suspected: bool
    reason: str = ""


@dataclass(frozen=True)
class Contact:
    email: str
    name: str = ""
    policy: str = "default"
    tone: str = "polite and concise"
    note: str = ""


@dataclass(frozen=True)
class Decision:
    label: Optional[str]
    archive: bool
    draft: bool
    notify: Optional[str]  # "now" | "digest" | None
    tier: int
    reasons: Tuple[str, ...]
