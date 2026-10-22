"""Own SQLite file; reuses the comms Store for settings and the hash-chained audit log."""

from __future__ import annotations

import calendar
import datetime as dt
from typing import Any, Dict, List, Optional

from layla_comms.store import Store

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

FIN_SCHEMA = """
CREATE TABLE IF NOT EXISTS fin_accounts(
  name TEXT PRIMARY KEY, kind TEXT, balance REAL, low REAL, updated REAL);
CREATE TABLE IF NOT EXISTS fin_expenses(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, amount REAL, currency TEXT,
  category TEXT, vendor TEXT, account TEXT, note TEXT, source TEXT);
CREATE TABLE IF NOT EXISTS fin_subs(
  name TEXT PRIMARY KEY, amount REAL, currency TEXT, cycle TEXT, next_due TEXT, category TEXT);
CREATE TABLE IF NOT EXISTS fin_credits(
  name TEXT PRIMARY KEY, unit TEXT, remaining REAL, total REAL, low REAL, updated REAL, source TEXT);
CREATE TABLE IF NOT EXISTS fin_credit_log(ts REAL, name TEXT, remaining REAL);
CREATE TABLE IF NOT EXISTS fin_alerts(key TEXT PRIMARY KEY, ts REAL);
"""

CYCLES = ("weekly", "monthly", "yearly")


def add_cycle(day: dt.date, cycle: str) -> dt.date:
    if cycle == "weekly":
        return day + dt.timedelta(days=7)
    months = 12 if cycle == "yearly" else 1
    m0 = day.month - 1 + months
    y, m = day.year + m0 // 12, m0 % 12 + 1
    return dt.date(y, m, min(day.day, calendar.monthrange(y, m)[1]))


class FinStore(Store):
    def __init__(self, path: str, clock=None):
        if clock is None:
            super().__init__(path)
        else:
            super().__init__(path, clock)
        with self._lock:
            self._db.executescript(FIN_SCHEMA)
            self._db.commit()

    def today(self) -> dt.date:
        return dt.datetime.fromtimestamp(self.clock(), IST).date()

    # ---- accounts -------------------------------------------------------
    def set_account(self, name: str, kind: Optional[str] = None, balance: Optional[float] = None,
                    low: Optional[float] = None) -> None:
        n = name.strip().lower()
        cur = self._q("SELECT * FROM fin_accounts WHERE name=?", (n,))
        c = dict(cur[0]) if cur else {"kind": "bank", "balance": None, "low": None}
        self._q("INSERT INTO fin_accounts(name,kind,balance,low,updated) VALUES(?,?,?,?,?)"
                " ON CONFLICT(name) DO UPDATE SET kind=excluded.kind, balance=excluded.balance,"
                " low=excluded.low, updated=excluded.updated",
                (n, kind or c["kind"], c["balance"] if balance is None else balance,
                 c["low"] if low is None else low, self.clock()))

    def accounts(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self._q("SELECT * FROM fin_accounts ORDER BY name")]

    def adjust_balance(self, name: str, delta: float) -> None:
        n = name.strip().lower()
        r = self._q("SELECT balance FROM fin_accounts WHERE name=?", (n,))
        if r and r[0]["balance"] is not None:
            self._q("UPDATE fin_accounts SET balance=balance+?, updated=? WHERE name=?", (delta, self.clock(), n))

    # ---- expenses -------------------------------------------------------
    def add_expense(self, amount: float, category: str = "other", vendor: str = "", account: str = "",
                    note: str = "", currency: str = "INR", source: str = "manual") -> int:
        self._q("INSERT INTO fin_expenses(ts,amount,currency,category,vendor,account,note,source)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (self.clock(), amount, currency.upper(), category.lower(), vendor.lower(),
                 account.strip().lower(), note[:200], source))
        if account:
            self.adjust_balance(account, -amount)
        return int(self._q("SELECT MAX(id) m FROM fin_expenses")[0]["m"])

    def spent_between(self, start: float, end: float) -> Dict[str, float]:
        rows = self._q("SELECT currency, SUM(amount) s FROM fin_expenses WHERE ts>=? AND ts<? GROUP BY currency",
                       (start, end))
        return {r["currency"]: r["s"] for r in rows}

    def spent_by_category(self, start: float, end: float) -> List[Dict[str, Any]]:
        return [dict(r) for r in self._q(
            "SELECT category, currency, SUM(amount) s FROM fin_expenses WHERE ts>=? AND ts<?"
            " GROUP BY category, currency ORDER BY s DESC", (start, end))]

    def day_bounds(self, day: dt.date) -> tuple:
        s = dt.datetime.combine(day, dt.time(0), IST).timestamp()
        return s, s + 86400

    def month_bounds(self, day: dt.date) -> tuple:
        first = day.replace(day=1)
        nxt = add_cycle(first, "monthly")
        return (dt.datetime.combine(first, dt.time(0), IST).timestamp(),
                dt.datetime.combine(nxt, dt.time(0), IST).timestamp())

    # ---- subscriptions --------------------------------------------------
    def set_sub(self, name: str, amount: float, cycle: str, next_due: str, currency: str = "INR",
                category: str = "subscription") -> None:
        if cycle not in CYCLES:
            raise ValueError("cycle must be weekly, monthly or yearly")
        dt.date.fromisoformat(next_due)
        self._q("INSERT INTO fin_subs(name,amount,currency,cycle,next_due,category) VALUES(?,?,?,?,?,?)"
                " ON CONFLICT(name) DO UPDATE SET amount=excluded.amount, currency=excluded.currency,"
                " cycle=excluded.cycle, next_due=excluded.next_due, category=excluded.category",
                (name.strip().lower(), amount, currency.upper(), cycle, next_due, category))

    def subs(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self._q("SELECT * FROM fin_subs ORDER BY next_due")]

    def mark_paid(self, name: str) -> Optional[str]:
        """Record the payment as an expense and roll next_due forward one cycle."""
        r = self._q("SELECT * FROM fin_subs WHERE name=?", (name.strip().lower(),))
        if not r:
            return None
        s = dict(r[0])
        nxt = add_cycle(dt.date.fromisoformat(s["next_due"]), s["cycle"]).isoformat()
        self._q("UPDATE fin_subs SET next_due=? WHERE name=?", (nxt, s["name"]))
        self.add_expense(s["amount"], s["category"], s["name"], note="subscription", currency=s["currency"],
                         source="subscription")
        return nxt

    def delete_sub(self, name: str) -> bool:
        n = len(self._q("SELECT 1 FROM fin_subs WHERE name=?", (name.strip().lower(),)))
        self._q("DELETE FROM fin_subs WHERE name=?", (name.strip().lower(),))
        return bool(n)

    # ---- credits --------------------------------------------------------
    def set_credit(self, name: str, remaining: Optional[float] = None, total: Optional[float] = None,
                   low: Optional[float] = None, unit: Optional[str] = None, source: str = "manual") -> None:
        n = name.strip().lower()
        cur = self._q("SELECT * FROM fin_credits WHERE name=?", (n,))
        c = dict(cur[0]) if cur else {"unit": "credits", "remaining": None, "total": None, "low": None}
        rem = c["remaining"] if remaining is None else remaining
        self._q("INSERT INTO fin_credits(name,unit,remaining,total,low,updated,source) VALUES(?,?,?,?,?,?,?)"
                " ON CONFLICT(name) DO UPDATE SET unit=excluded.unit, remaining=excluded.remaining,"
                " total=excluded.total, low=excluded.low, updated=excluded.updated, source=excluded.source",
                (n, unit or c["unit"], rem, c["total"] if total is None else total,
                 c["low"] if low is None else low, self.clock(), source))
        if remaining is not None:
            self._q("INSERT INTO fin_credit_log(ts,name,remaining) VALUES(?,?,?)", (self.clock(), n, remaining))

    def credits(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self._q("SELECT * FROM fin_credits ORDER BY name")]

    def credit_burn_per_day(self, name: str, days: int = 7) -> Optional[float]:
        """Average units consumed per day over the window; None when there is not enough history."""
        since = self.clock() - days * 86400
        rows = self._q("SELECT ts, remaining FROM fin_credit_log WHERE name=? AND ts>=? ORDER BY ts",
                       (name.strip().lower(), since))
        if len(rows) < 2:
            return None
        span = (rows[-1]["ts"] - rows[0]["ts"]) / 86400
        if span < 0.2:
            return None
        used = rows[0]["remaining"] - rows[-1]["remaining"]
        return max(used, 0.0) / span

    # ---- alert de-duplication -------------------------------------------
    def should_alert(self, key: str, cooldown_s: float) -> bool:
        r = self._q("SELECT ts FROM fin_alerts WHERE key=?", (key,))
        if r and self.clock() - r[0]["ts"] < cooldown_s:
            return False
        self._q("INSERT INTO fin_alerts(key,ts) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET ts=excluded.ts",
                (key, self.clock()))
        return True
