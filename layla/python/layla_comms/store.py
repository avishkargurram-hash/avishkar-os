"""SQLite persistence: idempotency, contacts, draft queue, settings, and a
hash-chained audit log. Own database file; shares nothing with Layla."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .types import ACTIONS, POLICIES, Contact

SCHEMA = """
CREATE TABLE IF NOT EXISTS processed(
  msg_id TEXT PRIMARY KEY, ts REAL, category TEXT, summary TEXT,
  sender TEXT, subject TEXT, notify TEXT, digested INTEGER DEFAULT 0, tier INTEGER);
CREATE TABLE IF NOT EXISTS contacts(
  email TEXT PRIMARY KEY, name TEXT, policy TEXT, tone TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS drafts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, msg_id TEXT, thread_id TEXT,
  to_email TEXT, subject TEXT, body TEXT, gmail_draft_id TEXT,
  status TEXT);
CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS audit(
  seq INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, kind TEXT, detail TEXT,
  prev TEXT, hash TEXT);
"""


class Store:
    def __init__(self, path: str, clock: Callable[[], float] = time.time):
        self.clock = clock
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.executescript(SCHEMA)
            self._db.commit()

    def _q(self, sql: str, args: tuple = ()) -> List[sqlite3.Row]:
        with self._lock:
            cur = self._db.execute(sql, args)
            rows = cur.fetchall()
            self._db.commit()
            return rows

    # ---- settings: kill switch + per-action live/shadow -----------------
    def get_setting(self, k: str, default: str = "") -> str:
        r = self._q("SELECT v FROM settings WHERE k=?", (k,))
        return r[0]["v"] if r else default

    def set_setting(self, k: str, v: str) -> None:
        self._q("INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))
        self.audit("setting", {"k": k, "v": v})

    def killed(self) -> bool:
        return self.get_setting("kill", "0") == "1"

    def action_live(self, action: str) -> bool:
        """Everything is shadow unless explicitly enabled."""
        if action not in ACTIONS:
            return False
        return self.get_setting(f"live:{action}", "0") == "1"

    # ---- idempotency -----------------------------------------------------
    def seen(self, msg_id: str) -> bool:
        return bool(self._q("SELECT 1 FROM processed WHERE msg_id=?", (msg_id,)))

    def record_processed(self, msg_id: str, category: str, summary: str, sender: str,
                         subject: str, notify: Optional[str], tier: int) -> None:
        self._q("INSERT OR IGNORE INTO processed(msg_id,ts,category,summary,sender,subject,notify,tier)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (msg_id, self.clock(), category, summary, sender, subject, notify, tier))

    def undigested(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self._q(
            "SELECT * FROM processed WHERE digested=0 AND notify IS NOT NULL ORDER BY ts")]

    def mark_digested(self, msg_ids: List[str]) -> None:
        for m in msg_ids:
            self._q("UPDATE processed SET digested=1 WHERE msg_id=?", (m,))

    # ---- contacts --------------------------------------------------------
    def get_contact(self, email: str) -> Contact:
        email = email.strip().lower()
        r = self._q("SELECT * FROM contacts WHERE email=?", (email,))
        if not r and "@" in email:
            labels = email.rsplit("@", 1)[1].split(".")
            for i in range(len(labels) - 1):
                r = self._q("SELECT * FROM contacts WHERE email=?", ("@" + ".".join(labels[i:]),))
                if r:
                    break
        if not r:
            return Contact(email=email)
        x = r[0]
        return Contact(email=email, name=x["name"] or "", policy=x["policy"] or "default",
                       tone=x["tone"] or "polite and concise", note=x["note"] or "")

    def set_contact(self, email: str, policy: str = "default", name: str = "",
                    tone: str = "polite and concise", note: str = "") -> None:
        if policy not in POLICIES:
            raise ValueError(f"policy must be one of {POLICIES}")
        self._q("INSERT INTO contacts(email,name,policy,tone,note) VALUES(?,?,?,?,?) "
                "ON CONFLICT(email) DO UPDATE SET name=excluded.name, policy=excluded.policy,"
                " tone=excluded.tone, note=excluded.note",
                (email.strip().lower(), name, policy, tone, note))
        self.audit("contact", {"email": email, "policy": policy})

    # ---- draft queue -----------------------------------------------------
    def add_draft(self, msg_id: str, thread_id: str, to_email: str, subject: str,
                  body: str, gmail_draft_id: str, status: str) -> int:
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO drafts(ts,msg_id,thread_id,to_email,subject,body,gmail_draft_id,status)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (self.clock(), msg_id, thread_id, to_email, subject, body, gmail_draft_id, status))
            self._db.commit()
            return int(cur.lastrowid)

    def list_drafts(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        if status:
            rows = self._q("SELECT * FROM drafts WHERE status=? ORDER BY id", (status,))
        else:
            rows = self._q("SELECT * FROM drafts ORDER BY id")
        return [dict(r) for r in rows]

    # ---- audit: hash chain ----------------------------------------------
    def audit(self, kind: str, detail: Dict[str, Any]) -> None:
        with self._lock:
            row = self._db.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
            prev = row["hash"] if row else "genesis"
            ts = self.clock()
            blob = json.dumps(detail, sort_keys=True, default=str)
            h = hashlib.sha256(f"{prev}|{ts}|{kind}|{blob}".encode()).hexdigest()
            self._db.execute("INSERT INTO audit(ts,kind,detail,prev,hash) VALUES(?,?,?,?,?)",
                             (ts, kind, blob, prev, h))
            self._db.commit()

    def audit_rows(self, limit: int = 50) -> List[Dict[str, Any]]:
        return [dict(r) for r in self._q("SELECT * FROM audit ORDER BY seq DESC LIMIT ?", (limit,))]

    def verify_audit(self) -> bool:
        prev = "genesis"
        for r in self._q("SELECT * FROM audit ORDER BY seq"):
            h = hashlib.sha256(f"{prev}|{r['ts']}|{r['kind']}|{r['detail']}".encode()).hexdigest()
            if r["prev"] != prev or r["hash"] != h:
                return False
            prev = r["hash"]
        return True
