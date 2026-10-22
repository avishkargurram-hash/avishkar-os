"""Daily digest built purely from stored summaries (no new model call and
no raw email text), so it cannot carry an injection to the owner."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from .effects import Effects
from .store import Store

ORDER = ["urgent", "needs_reply", "needs_human", "spam_suspect", "fyi",
         "newsletter", "promo", "notification"]
TITLES = {"urgent": "Urgent", "needs_reply": "Needs a reply", "needs_human": "Needs you",
          "spam_suspect": "Possible spam", "fyi": "FYI", "newsletter": "Newsletters",
          "promo": "Promotions", "notification": "Notifications"}


def _safe(s: str, n: int) -> str:
    return " ".join(s.split())[:n]


def build(store: Store) -> str:
    items = store.undigested()
    if not items:
        return ""
    groups: Dict[str, List[dict]] = defaultdict(list)
    for it in items:
        groups[it["category"]].append(it)
    pending = store.list_drafts("drafted") + store.list_drafts("shadow")
    lines = [f"Email digest: {len(items)} new"]
    if pending:
        lines.append(f"{len(pending)} reply draft(s) waiting in Gmail Drafts for your review.")
    for cat in ORDER:
        rows = groups.get(cat)
        if not rows:
            continue
        lines.append(f"\n{TITLES[cat]} ({len(rows)})")
        limit = 3 if cat in ("newsletter", "promo", "notification") else 10
        for r in rows[:limit]:
            lines.append(f"- {_safe(r['sender'], 40)}: {_safe(r['subject'], 70)}"
                         + (f" -- {_safe(r['summary'], 120)}" if r["summary"] else ""))
        if len(rows) > limit:
            lines.append(f"  ...and {len(rows) - limit} more")
    return "\n".join(lines)


def send_digest(store: Store, fx: Effects) -> bool:
    text = build(store)
    if not text:
        return False
    ok = fx.notify(text)
    if ok:
        store.mark_digested([r["msg_id"] for r in store.undigested()])
    return ok
