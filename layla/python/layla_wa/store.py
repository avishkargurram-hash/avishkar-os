"""Own SQLite file. Reuses the comms Store for settings and the hash-chained
audit log; adds the WhatsApp tables."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from layla_comms.store import Store

WA_SCHEMA = """
CREATE TABLE IF NOT EXISTS wa_msgs(
  id TEXT PRIMARY KEY, ts REAL, conv TEXT, title TEXT, sender TEXT,
  is_group INTEGER, text TEXT, status TEXT, reason TEXT);
CREATE TABLE IF NOT EXISTS wa_replies(
  id TEXT PRIMARY KEY, ts REAL, conv TEXT, title TEXT, text TEXT,
  category TEXT, status TEXT, expires REAL, sent_ts REAL);
CREATE TABLE IF NOT EXISTS wa_leads(
  conv TEXT PRIMARY KEY, ts REAL, title TEXT, name TEXT, interest TEXT, schedule TEXT);
"""


class WaStore(Store):
    def __init__(self, path: str, clock=None):
        if clock is None:
            super().__init__(path)
        else:
            super().__init__(path, clock)
        with self._lock:
            self._db.executescript(WA_SCHEMA)
            self._db.commit()

    # ---- switches -------------------------------------------------------
    def enabled(self) -> bool:
        return self.get_setting("wa:enabled", "0") == "1"

    def set_enabled(self, on: bool, who: str = "telegram") -> None:
        self.set_setting("wa:enabled", "1" if on else "0")
        self.audit("wa_switch", {"enabled": on, "by": who})

    def _list(self, key: str) -> List[str]:
        try:
            v = json.loads(self.get_setting(key, "[]"))
            return [str(x) for x in v] if isinstance(v, list) else []
        except ValueError:
            return []

    def _set_list(self, key: str, items: List[str]) -> None:
        self.set_setting(key, json.dumps(sorted(set(items))))

    def groups(self) -> List[str]:
        return self._list("wa:groups")

    def add_group(self, name: str) -> None:
        self._set_list("wa:groups", self.groups() + [name.strip().lower()])

    def remove_group(self, name: str) -> bool:
        cur = self.groups()
        n = name.strip().lower()
        if n not in cur:
            return False
        self._set_list("wa:groups", [g for g in cur if g != n])
        return True

    def muted(self) -> List[str]:
        return self._list("wa:muted")

    def mute(self, name: str) -> None:
        self._set_list("wa:muted", self.muted() + [name.strip().lower()])

    def unmute(self, name: str) -> bool:
        cur = self.muted()
        n = name.strip().lower()
        if n not in cur:
            return False
        self._set_list("wa:muted", [m for m in cur if m != n])
        return True

    # ---- messages -------------------------------------------------------
    def msg_seen(self, mid: str) -> bool:
        return bool(self._q("SELECT 1 FROM wa_msgs WHERE id=?", (mid,)))

    def record_msg(self, mid: str, conv: str, title: str, sender: str, is_group: bool,
                   text: str, status: str, reason: str) -> None:
        self._q("INSERT OR IGNORE INTO wa_msgs(id,ts,conv,title,sender,is_group,text,status,reason)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (mid, self.clock(), conv, title, sender, int(is_group), text[:1000], status, reason))

    # ---- replies --------------------------------------------------------
    def add_reply(self, rid: str, conv: str, title: str, text: str, category: str, ttl: float) -> None:
        now = self.clock()
        self._q("INSERT OR REPLACE INTO wa_replies(id,ts,conv,title,text,category,status,expires)"
                " VALUES(?,?,?,?,?,?,?,?)", (rid, now, conv, title, text, category, "pending", now + ttl))

    def get_reply(self, rid: str) -> Optional[Dict[str, Any]]:
        r = self._q("SELECT * FROM wa_replies WHERE id=?", (rid,))
        return dict(r[0]) if r else None

    def set_reply_status(self, rid: str, status: str) -> None:
        if status == "sent":
            self._q("UPDATE wa_replies SET status=?, sent_ts=? WHERE id=?", (status, self.clock(), rid))
        else:
            self._q("UPDATE wa_replies SET status=? WHERE id=?", (status, rid))

    def claim_commit(self, rid: str) -> bool:
        """Atomic pending -> committed; a second commit for the same reply fails."""
        with self._lock:
            cur = self._db.execute("UPDATE wa_replies SET status='committed' WHERE id=? AND status='pending'", (rid,))
            self._db.commit()
            return cur.rowcount == 1

    def count_replies_since(self, since: float, conv: Optional[str] = None) -> int:
        live = "('pending','committed','sent')"
        if conv is None:
            r = self._q(f"SELECT COUNT(*) c FROM wa_replies WHERE ts>=? AND status IN {live}", (since,))
        else:
            r = self._q(f"SELECT COUNT(*) c FROM wa_replies WHERE ts>=? AND conv=? AND status IN {live}",
                        (since, conv))
        return int(r[0]["c"])

    def recent_activity(self, limit: int = 8) -> List[Dict[str, Any]]:
        """Newest replies first, for the owner's app: who, what was sent, and how it went."""
        rows = self._q("SELECT ts,title,text,category,status FROM wa_replies ORDER BY ts DESC LIMIT ?", (int(limit),))
        return [{"ts": r["ts"], "title": r["title"], "text": r["text"], "category": r["category"],
                 "status": r["status"]} for r in rows]

    def count_category_since(self, since: float, category: str) -> int:
        r = self._q("SELECT COUNT(*) c FROM wa_replies WHERE ts>=? AND category=? "
                    "AND status IN ('pending','committed','sent')", (since, category))
        return int(r[0]["c"])

    def recent_sent(self, conv: str, limit: int = 4) -> List[str]:
        rows = self._q("SELECT text FROM wa_replies WHERE conv=? AND status='sent' ORDER BY ts DESC LIMIT ?",
                       (conv, limit))
        return [r["text"] for r in reversed(rows)]

    # ---- leads ----------------------------------------------------------
    def get_lead(self, conv: str) -> Dict[str, str]:
        r = self._q("SELECT * FROM wa_leads WHERE conv=?", (conv,))
        return dict(r[0]) if r else {}

    def upsert_lead(self, conv: str, title: str, name: str, interest: str, schedule: str) -> bool:
        """Merge non-empty fields; return True when something new was learned."""
        cur = self.get_lead(conv)
        merged = {k: (v or cur.get(k) or "") for k, v in
                  (("name", name), ("interest", interest), ("schedule", schedule))}
        changed = any(merged[k] != (cur.get(k) or "") for k in merged)
        self._q("INSERT INTO wa_leads(conv,ts,title,name,interest,schedule) VALUES(?,?,?,?,?,?)"
                " ON CONFLICT(conv) DO UPDATE SET ts=excluded.ts, title=excluded.title, name=excluded.name,"
                " interest=excluded.interest, schedule=excluded.schedule",
                (conv, self.clock(), title, merged["name"], merged["interest"], merged["schedule"]))
        return changed
