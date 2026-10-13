"""Owner commands: /fin ... Reached through the layla_wa Telegram controller (single getUpdates poller)."""

from __future__ import annotations

from typing import List, Optional

from .monitor import Monitor, money
from .parse import parse_alert
from .store import CYCLES, FinStore

HELP = (
    "/fin status - digest: spend, balances, credits, renewals\n"
    "/fin month - this month by category\n"
    "/fin spent <amt> <category> [vendor] [@account]\n"
    "/fin account <name> [bank|upi|card|cash] [low <amt>]\n"
    "/fin bal <account> <amt>\n"
    "/fin credit set <name> <remaining> [total <n>] [unit <u>]\n"
    "/fin credit low <name> <n>\n"
    "/fin sub add <name> <amt> <weekly|monthly|yearly> <YYYY-MM-DD>\n"
    "/fin sub list | paid <name> | del <name>\n"
    "/fin sms <bank or UPI alert text>\n"
    "Names are single words (e.g. hostinger, hdfc)."
)


def _amt(s: str) -> float:
    v = float(s.replace(",", ""))
    if v < 0 or v != v or v in (float("inf"),):
        raise ValueError("amount must be a positive number")
    return v


def _sms(st: FinStore, text: str) -> str:
    p = parse_alert(text)
    if not p:
        return "Could not read that alert. Use /fin spent <amt> <category> instead."
    low = text.lower()
    accts = st.accounts()
    hit = [a for a in accts if a["name"] in low]
    acct = hit[0]["name"] if len(hit) == 1 else (accts[0]["name"] if len(accts) == 1 else "")
    if p["direction"] == "debit":
        st.add_expense(p["amount"], "other", p["vendor"], acct, "bank/UPI alert", source="sms")
    elif acct:
        st.adjust_balance(acct, p["amount"])
    if acct and p["balance"] is not None:
        st.set_account(acct, balance=p["balance"])
    where = f" on {acct}" if acct else " (no matching account, balance not updated)"
    what = "Logged spend" if p["direction"] == "debit" else "Noted credit"
    return f"{what} {money(p['amount'])}{where}" + (f", {p['vendor']}" if p["vendor"] else "")


def handle_command(st: FinStore, text: str, mon: Optional[Monitor] = None) -> Optional[str]:
    t = text.strip()
    if not (t == "/fin" or t.startswith("/fin ") or t.startswith("/fin@")):
        return None
    a: List[str] = t.split()[1:]
    try:
        return _run(st, a, t, mon)
    except (ValueError, IndexError) as e:
        return f"Could not do that: {e}\n\n{HELP}" if str(e) else HELP


def _run(st: FinStore, a: List[str], raw: str, mon: Optional[Monitor]) -> str:
    cmd = a[0].lower() if a else ""
    mon = mon or Monitor(st, notifier=None)
    if cmd in ("status", ""):
        return mon.digest() if cmd else HELP
    if cmd == "month":
        s, e = st.month_bounds(st.today())
        tot = st.spent_between(s, e)
        rows = st.spent_by_category(s, e)
        lines = ["This month: " + (", ".join(money(v, k) for k, v in tot.items()) or "nothing")]
        lines += [f"{r['category']}: {money(r['s'], r['currency'])}" for r in rows[:10]]
        return "\n".join(lines)
    if cmd == "spent":
        amount, cat = _amt(a[1]), (a[2] if len(a) > 2 else "other")
        acct = next((x[1:] for x in a[3:] if x.startswith("@")), "")
        vendor = " ".join(x for x in a[3:] if not x.startswith("@"))
        st.add_expense(amount, cat, vendor, acct)
        return f"Logged {money(amount)} on {cat}" + (f" from {acct}" if acct else "")
    if cmd == "account":
        name = a[1]
        kind = next((x for x in a[2:] if x in ("bank", "upi", "card", "cash")), None)
        low = _amt(a[a.index("low") + 1]) if "low" in a else None
        st.set_account(name, kind=kind, low=low)
        return f"Account {name.lower()} saved."
    if cmd == "bal":
        st.set_account(a[1], balance=_amt(a[2]))
        return f"{a[1].lower()} balance set to {money(_amt(a[2]))}."
    if cmd == "credit":
        sub = a[1].lower()
        if sub == "set":
            kw = {a[i]: a[i + 1] for i in range(3, len(a) - 1, 2)}
            st.set_credit(a[2], remaining=_amt(a[3]), total=_amt(kw["total"]) if "total" in kw else None,
                          unit=kw.get("unit"))
            return f"{a[2].lower()} credits set to {_amt(a[3]):,.0f}."
        if sub == "low":
            st.set_credit(a[2], low=_amt(a[3]))
            return f"{a[2].lower()} alert threshold set to {_amt(a[3]):,.0f}."
        raise ValueError("credit set|low")
    if cmd == "sub":
        sub = a[1].lower() if len(a) > 1 else "list"
        if sub == "add":
            if a[4].lower() not in CYCLES:
                raise ValueError("cycle must be weekly, monthly or yearly")
            st.set_sub(a[2], _amt(a[3]), a[4].lower(), a[5])
            return f"Subscription {a[2].lower()} saved, next due {a[5]}."
        if sub == "list":
            rows = st.subs()
            return "\n".join(f"{s['next_due']} {s['name']} {money(s['amount'], s['currency'])} {s['cycle']}"
                             for s in rows) or "No subscriptions."
        if sub == "paid":
            nxt = st.mark_paid(a[2])
            return f"Recorded. Next due {nxt}." if nxt else "No such subscription."
        if sub == "del":
            return "Removed." if st.delete_sub(a[2]) else "No such subscription."
        raise ValueError("sub add|list|paid|del")
    if cmd == "sms":
        body = raw.split(None, 2)[2] if len(raw.split(None, 2)) > 2 else ""
        return _sms(st, body)
    return HELP
