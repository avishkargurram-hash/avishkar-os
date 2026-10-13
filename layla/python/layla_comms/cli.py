"""Operator CLI.  python -m layla_comms.cli <command>

Env: COMMS_DB, GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN,
OWNER_EMAIL, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL,
TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (optional).
"""

from __future__ import annotations

import argparse
import os
import sys

from .digest import send_digest
from .effects import Effects
from .gmail import GmailClient
from .llm import Model, openai_compatible
from .notify import ConsoleNotifier, TelegramNotifier
from .store import Store
from .triage import Triage
from .types import ACTIONS, POLICIES


def _store() -> Store:
    return Store(os.environ.get("COMMS_DB", "comms.db"))


def _notifier():
    t, c = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    return TelegramNotifier(t, c) if t and c else ConsoleNotifier()


def _gmail() -> GmailClient:
    e = os.environ
    return GmailClient(e["GMAIL_CLIENT_ID"], e["GMAIL_CLIENT_SECRET"], e["GMAIL_REFRESH_TOKEN"])


def cmd_poll(a) -> int:
    st, gm = _store(), _gmail()
    model = Model(openai_compatible(os.environ["LLM_BASE_URL"], os.environ["LLM_API_KEY"],
                                    os.environ["LLM_MODEL"]))
    tri = Triage(st, model, Effects(st, gm, _notifier()), os.environ.get("OWNER_EMAIL", ""))
    n = 0
    for mid in gm.list_recent(limit=a.limit):
        if st.seen(mid):
            continue
        print(mid, tri.process(gm.fetch(mid)))
        n += 1
    print(f"processed {n}")
    return 0


def cmd_digest(a) -> int:
    st = _store()
    print("sent" if send_digest(st, Effects(st, _gmail(), _notifier())) else "nothing to send")
    return 0


def cmd_status(a) -> int:
    st = _store()
    print("kill switch:", "ON" if st.killed() else "off")
    for act in ACTIONS:
        print(f"{act}: {'LIVE' if st.action_live(act) else 'shadow'}")
    print("audit chain intact:", st.verify_audit())
    print("drafts:", len(st.list_drafts()))
    return 0


def cmd_kill(a) -> int:
    _store().set_setting("kill", "1" if a.on == "on" else "0")
    return 0


def cmd_live(a) -> int:
    _store().set_setting(f"live:{a.action}", "1" if a.state == "on" else "0")
    return 0


def cmd_contact(a) -> int:
    _store().set_contact(a.email, a.policy, a.name or "")
    return 0


def cmd_audit(a) -> int:
    for r in reversed(_store().audit_rows(a.n)):
        print(r["seq"], r["kind"], r["detail"][:160])
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="layla_comms")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("poll"); s.add_argument("--limit", type=int, default=25); s.set_defaults(f=cmd_poll)
    sub.add_parser("digest").set_defaults(f=cmd_digest)
    sub.add_parser("status").set_defaults(f=cmd_status)
    s = sub.add_parser("kill"); s.add_argument("on", choices=["on", "off"]); s.set_defaults(f=cmd_kill)
    s = sub.add_parser("live"); s.add_argument("action", choices=ACTIONS)
    s.add_argument("state", choices=["on", "off"]); s.set_defaults(f=cmd_live)
    s = sub.add_parser("contact"); s.add_argument("email"); s.add_argument("policy", choices=POLICIES)
    s.add_argument("--name"); s.set_defaults(f=cmd_contact)
    s = sub.add_parser("audit"); s.add_argument("-n", type=int, default=30); s.set_defaults(f=cmd_audit)
    a = p.parse_args(argv)
    return a.f(a)


if __name__ == "__main__":
    sys.exit(main())
