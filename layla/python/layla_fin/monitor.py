"""Provider polling, threshold/renewal checks and the daily digest. Everything sends through
a notifier and is de-duplicated per key, so a restart or a tight loop never spams Telegram."""

from __future__ import annotations

import datetime as dt
import json
import threading
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from .store import IST, FinStore

DAY = 86400.0
ELEVEN_URL = "https://api.elevenlabs.io/v1/user/subscription"


def fetch_elevenlabs(api_key: str) -> Dict[str, Any]:
    req = urllib.request.Request(ELEVEN_URL, headers={"xi-api-key": api_key, "User-Agent": "layla-fin/1"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def money(v: float, cur: str = "INR") -> str:
    sym = {"INR": "Rs ", "USD": "$"}.get(cur, cur + " ")
    return f"{sym}{v:,.0f}" if abs(v) >= 100 or float(v).is_integer() else f"{sym}{v:,.2f}"


class Monitor:
    def __init__(self, st: FinStore, notifier, eleven_key: str = "", digest_hour: int = 9,
                 fetch: Callable[[str], Dict[str, Any]] = fetch_elevenlabs):
        self.st, self.notifier, self.key, self.digest_hour, self._fetch = st, notifier, eleven_key, digest_hour, fetch

    def _send(self, text: str) -> None:
        try:
            self.notifier.send(text)
        except Exception as e:
            self.st.audit("fin_notify_error", {"err": str(e)[:200]})

    def poll_providers(self) -> Optional[str]:
        """Pull ElevenLabs credits. Returns an error string on failure (never raises)."""
        if not self.key:
            return None
        try:
            d = self._fetch(self.key)
            limit, used = float(d["character_limit"]), float(d["character_count"])
        except Exception as e:
            self.st.audit("fin_poll_error", {"provider": "elevenlabs", "err": str(e)[:200]})
            return f"elevenlabs poll failed: {str(e)[:80]}"
        existing = {c["name"]: c for c in self.st.credits()}.get("elevenlabs")
        low = existing["low"] if existing and existing["low"] is not None else round(limit * 0.10)
        self.st.set_credit("elevenlabs", remaining=limit - used, total=limit, low=low, unit="credits", source="api")
        return None

    def checks(self) -> List[str]:
        """Return the alert texts that are due now (already de-duplicated and recorded)."""
        out: List[str] = []
        today = self.st.today()
        for a in self.st.accounts():
            if a["balance"] is not None and a["low"] is not None and a["balance"] < a["low"]:
                if self.st.should_alert(f"acct:{a['name']}", DAY):
                    out.append(f"[Low balance] {a['name']} is {money(a['balance'])} "
                               f"(threshold {money(a['low'])})")
        for c in self.st.credits():
            if c["remaining"] is None:
                continue
            if c["low"] is not None and c["remaining"] < c["low"]:
                if self.st.should_alert(f"credit:{c['name']}", DAY):
                    out.append(f"[Low credits] {c['name']}: {c['remaining']:,.0f} {c['unit']} left "
                               f"(threshold {c['low']:,.0f})")
                continue
            burn = self.st.credit_burn_per_day(c["name"])
            if burn and burn > 0 and c["remaining"] / burn < 5:
                if self.st.should_alert(f"runway:{c['name']}", DAY):
                    out.append(f"[Credit runway] {c['name']} burns ~{burn:,.0f}/day; "
                               f"{c['remaining']:,.0f} left is about {c['remaining'] / burn:.1f} days")
        for s in self.st.subs():
            left = (dt.date.fromisoformat(s["next_due"]) - today).days
            if left <= 3:
                when = "is overdue by %d day(s)" % -left if left < 0 else ("is due today" if left == 0
                                                                          else f"is due in {left} day(s)")
                if self.st.should_alert(f"sub:{s['name']}:{s['next_due']}:{min(left, -1) if left < 0 else left}", DAY):
                    out.append(f"[Renewal] {s['name']} {money(s['amount'], s['currency'])} {when} "
                               f"({s['next_due']}). Reply /fin sub paid {s['name']} once paid.")
        now_ist = dt.datetime.fromtimestamp(self.st.clock(), IST)
        if now_ist.hour >= self.digest_hour and self.st.should_alert(f"digest:{today.isoformat()}", 2 * DAY):
            out.append(self.digest())
        for text in out:
            self._send(text)
        return out

    def digest(self) -> str:
        today = self.st.today()
        y = today - dt.timedelta(days=1)
        ys, ye = self.st.day_bounds(y)
        ms, me = self.st.month_bounds(today)
        lines = [f"Finance digest {today.isoformat()}"]
        fmt = lambda d: ", ".join(money(v, k) for k, v in d.items()) or "nothing"  # noqa: E731
        lines.append(f"Yesterday: {fmt(self.st.spent_between(ys, ye))}")
        lines.append(f"Month to date: {fmt(self.st.spent_between(ms, me))}")
        top = self.st.spent_by_category(ms, me)[:3]
        if top:
            lines.append("Top: " + ", ".join(f"{r['category']} {money(r['s'], r['currency'])}" for r in top))
        for a in self.st.accounts():
            if a["balance"] is not None:
                lines.append(f"{a['name']} ({a['kind']}): {money(a['balance'])}")
        for c in self.st.credits():
            if c["remaining"] is not None:
                tot = f" of {c['total']:,.0f}" if c["total"] else ""
                burn = self.st.credit_burn_per_day(c["name"])
                run = f", ~{c['remaining'] / burn:.0f} days at current burn" if burn else ""
                lines.append(f"{c['name']}: {c['remaining']:,.0f}{tot} {c['unit']}{run}")
        soon = [s for s in self.st.subs() if (dt.date.fromisoformat(s["next_due"]) - today).days <= 7]
        for s in soon:
            lines.append(f"Due {s['next_due']}: {s['name']} {money(s['amount'], s['currency'])}")
        return "\n".join(lines)

    def tick(self) -> List[str]:
        self.poll_providers()
        return self.checks()


class MonitorThread(threading.Thread):
    def __init__(self, mon: Monitor, interval_s: int = 900):
        super().__init__(daemon=True)
        self.mon, self.interval = mon, interval_s
        self.stop_flag = threading.Event()

    def run(self) -> None:
        while not self.stop_flag.is_set():
            try:
                self.mon.tick()
            except Exception as e:
                self.mon.st.audit("fin_tick_error", {"err": str(e)[:200]})
            self.stop_flag.wait(self.interval)
