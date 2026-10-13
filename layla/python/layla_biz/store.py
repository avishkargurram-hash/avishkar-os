"""Own SQLite file. Reuses the comms Store for settings and the hash-chained audit log."""

from __future__ import annotations

from typing import Any, Dict, List

from layla_comms.store import Store

BIZ_SCHEMA = """
CREATE TABLE IF NOT EXISTS biz_leads(
  caller TEXT PRIMARY KEY, ts REAL, name TEXT, phone TEXT, interest TEXT,
  details TEXT, preferred_time TEXT, callback INTEGER DEFAULT 0, status TEXT DEFAULT 'new');
CREATE TABLE IF NOT EXISTS biz_calls(ts REAL, caller TEXT, tool TEXT);
CREATE INDEX IF NOT EXISTS biz_calls_ts ON biz_calls(ts);
"""

LEAD_FIELDS = ("name", "phone", "interest", "details", "preferred_time")


class BizStore(Store):
    def __init__(self, path: str, clock=None):
        if clock is None:
            super().__init__(path)
        else:
            super().__init__(path, clock)
        with self._lock:
            self._db.executescript(BIZ_SCHEMA)
            self._db.commit()

    def enabled(self) -> bool:
        return self.get_setting("biz:enabled", "0") == "1"

    def set_enabled(self, on: bool, who: str = "telegram") -> None:
        self.set_setting("biz:enabled", "1" if on else "0")
        self.audit("biz_switch", {"enabled": on, "by": who})

    def note_call(self, caller: str, tool: str) -> None:
        self._q("INSERT INTO biz_calls(ts,caller,tool) VALUES(?,?,?)", (self.clock(), caller, tool))

    def calls_since(self, since: float, caller: str = "") -> int:
        if caller:
            r = self._q("SELECT COUNT(*) c FROM biz_calls WHERE ts>=? AND caller=?", (since, caller))
        else:
            r = self._q("SELECT COUNT(*) c FROM biz_calls WHERE ts>=?", (since,))
        return int(r[0]["c"])

    def get_lead(self, caller: str) -> Dict[str, Any]:
        r = self._q("SELECT * FROM biz_leads WHERE caller=?", (caller,))
        return dict(r[0]) if r else {}

    def upsert_lead(self, caller: str, fields: Dict[str, str], callback: bool = False) -> bool:
        """Merge non-empty fields into the caller's lead; True when anything new was learned."""
        cur = self.get_lead(caller)
        merged = {k: (fields.get(k) or cur.get(k) or "") for k in LEAD_FIELDS}
        cb = int(callback or bool(cur.get("callback")))
        changed = (not cur) or any(merged[k] != (cur.get(k) or "") for k in LEAD_FIELDS) \
            or cb != int(cur.get("callback") or 0)
        self._q("INSERT INTO biz_leads(caller,ts,name,phone,interest,details,preferred_time,callback)"
                " VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(caller) DO UPDATE SET ts=excluded.ts, name=excluded.name,"
                " phone=excluded.phone, interest=excluded.interest, details=excluded.details,"
                " preferred_time=excluded.preferred_time, callback=excluded.callback",
                (caller, self.clock(), merged["name"], merged["phone"], merged["interest"],
                 merged["details"], merged["preferred_time"], cb))
        return changed

    def recent_leads(self, limit: int = 10) -> List[Dict[str, Any]]:
        return [dict(r) for r in self._q("SELECT * FROM biz_leads ORDER BY ts DESC LIMIT ?", (limit,))]
