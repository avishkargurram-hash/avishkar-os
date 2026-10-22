"""Screenpipe Local Activity Memory (Pillar 4: Screenpipe).

Tracks active application windows, user digital activity timelines, and screen text
in a local SQLite database on Windows Workstation.
"""

from __future__ import annotations

import datetime
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

DB_DIR = os.path.expanduser(r"~\.layla\screenpipe")
DB_PATH = os.path.join(DB_DIR, "activity.db")

_lock = threading.Lock()


def _ensure_db() -> None:
    os.makedirs(DB_DIR, exist_ok=True)
    with _lock:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pc_activity_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    process_name TEXT,
                    window_title TEXT NOT NULL,
                    category TEXT,
                    summary_text TEXT,
                    ocr_sample TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_activity_time ON pc_activity_events(timestamp DESC)")
            conn.commit()


def log_activity_event(window_title: str, process_name: Optional[str] = None, summary_text: Optional[str] = None, ocr_sample: Optional[str] = None) -> None:
    """Logs an application focus or activity event to the local database."""
    if not window_title or not window_title.strip():
        return
    _ensure_db()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    # Simple category tagging based on title/process
    lower_t = window_title.lower()
    lower_p = (process_name or "").lower()
    cat = "general"
    if any(k in lower_t or k in lower_p for k in ("code", "visual studio", "terminal", "powershell", "cmd", "bash")):
        cat = "development"
    elif any(k in lower_t or k in lower_p for k in ("chrome", "edge", "firefox", "browser")):
        cat = "browsing"
    elif any(k in lower_t or k in lower_p for k in ("excel", "word", "document", "notion", "notepad", "pdf")):
        cat = "documents"
    elif any(k in lower_t or k in lower_p for k in ("slack", "teams", "telegram", "discord", "mail", "outlook")):
        cat = "communication"

    with _lock:
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("""
                    INSERT INTO pc_activity_events (timestamp, process_name, window_title, category, summary_text, ocr_sample)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (now_iso, process_name or "unknown", window_title.strip(), cat, summary_text, ocr_sample))
                conn.commit()
        except Exception as exc:
            print(f"[screenpipe] db insert error: {exc}")


def query_activity(query_terms: Optional[str] = None, hours: float = 24.0, limit: int = 15) -> Dict[str, Any]:
    """Queries recent PC digital activity matching terms within the time window."""
    _ensure_db()
    since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)).isoformat()
    with _lock:
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                if query_terms and query_terms.strip():
                    pattern = f"%{query_terms.strip()}%"
                    cursor = conn.execute("""
                        SELECT timestamp, process_name, window_title, category, summary_text
                        FROM pc_activity_events
                        WHERE timestamp >= ? AND (window_title LIKE ? OR process_name LIKE ? OR summary_text LIKE ?)
                        ORDER BY timestamp DESC
                        LIMIT ?
                    """, (since, pattern, pattern, pattern, limit))
                else:
                    cursor = conn.execute("""
                        SELECT timestamp, process_name, window_title, category, summary_text
                        FROM pc_activity_events
                        WHERE timestamp >= ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    """, (since, limit))
                rows = cursor.fetchall()

            events = [dict(r) for r in rows]
            # Build human readable narrative timeline
            lines = []
            for ev in events:
                ts = ev["timestamp"][11:16] # HH:MM
                lines.append(f"- [{ts}] {ev['category'].upper()}: {ev['window_title']} ({ev['process_name']})")

            summary_output = (
                f"PC Activity Timeline (Last {hours}h, {len(events)} events found):\n" +
                ("\n".join(lines) if lines else "No recorded activity matching query.")
            )

            return {
                "status": "success",
                "count": len(events),
                "events": events,
                "output": summary_output,
            }
        except Exception as exc:
            return {"status": "error", "error": f"Failed to query activity: {exc}"}


class ActivityMonitorThread(threading.Thread):
    """Background daemon polling the active foreground window and recording changes."""
    def __init__(self, poll_interval: float = 10.0):
        super().__init__(daemon=True, name="ScreenpipeMonitor")
        self.poll_interval = poll_interval
        self._last_title = ""
        self._running = True

    def run(self):
        print("[screenpipe] active window activity monitor started")
        _ensure_db()
        while self._running:
            try:
                title, proc = self._get_active_window_info()
                if title and title != self._last_title:
                    self._last_title = title
                    log_activity_event(title, proc)
            except Exception as exc:
                pass
            time.sleep(self.poll_interval)

    def _get_active_window_info(self) -> tuple[str, str]:
        try:
            import pygetwindow as gw
            win = gw.getActiveWindow()
            if win and win.title:
                return win.title.strip(), "application"
        except Exception:
            pass
        return "", ""

    def stop(self):
        self._running = False
