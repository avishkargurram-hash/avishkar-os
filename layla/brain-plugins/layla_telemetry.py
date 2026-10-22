"""Layla body telemetry -- Task 1, capability #9 (wearable / biological telemetry).

No wearable is paired yet, so this is the receiving side, ready for any
source: POST /telemetry/ingest accepts heart rate, resting HR, HRV, SpO2,
steps, sleep, weight, calories, stress from a phone health bridge (Android
Health Connect webhook apps, iOS Health Auto Export, Gadgetbridge, a
smartwatch script) or a manual post.

* Auth: the owner session cookie, OR a write-only ingest token
  ("Authorization: Bearer <token>"); only its sha256 is on the server
  (TELEMETRY_TOKEN_SHA256). The token can ONLY add samples -- it can't read
  anything or reach any other endpoint.
* Storage: its own SQLite file (telemetry.db), never mixed with chat memory;
  never sent to an LLM except as short numeric summaries when he asks.
* Signals for ambient autonomy (#5): resting HR well above his own 30-day
  baseline, a very short night, a sedentary day -- phrased as gentle
  check-ins, NEVER a diagnosis.

Kill switch: TELEMETRY=0. Never raises into the caller.
"""
import datetime as _dt
import hashlib
import hmac
import json
import os
import sqlite3
import threading
import time

from layla_plugin_util import IST, I, S, flag, tool

DB = os.environ.get("TELEMETRY_DB", "/opt/layla/telemetry.db")
MAX_SAMPLES = 5000
RATE_PER_MIN = 30

ALIASES = {
    "heart_rate": "heart_rate", "hr": "heart_rate", "heartrate": "heart_rate", "pulse": "heart_rate",
    "resting_heart_rate": "resting_hr", "resting_hr": "resting_hr", "restinghr": "resting_hr",
    "heart_rate_variability": "hrv", "hrv": "hrv", "heart_rate_variability_sdnn": "hrv",
    "spo2": "spo2", "blood_oxygen": "spo2", "blood_oxygen_saturation": "spo2", "oxygen_saturation": "spo2",
    "steps": "steps", "step_count": "steps", "stepcount": "steps",
    "sleep_minutes": "sleep_min", "sleep": "sleep_min", "sleep_analysis": "sleep_min", "sleep_min": "sleep_min",
    "weight": "weight_kg", "body_mass": "weight_kg", "weight_kg": "weight_kg",
    "active_energy": "active_kcal", "active_calories": "active_kcal", "calories": "active_kcal",
    "stress": "stress", "respiratory_rate": "resp_rate", "body_temperature": "body_temp",
}
RANGES = {"heart_rate": (25, 230), "resting_hr": (25, 150), "hrv": (1, 300), "spo2": (50, 100),
          "steps": (0, 100000), "sleep_min": (0, 1200), "weight_kg": (20, 300), "active_kcal": (0, 10000),
          "stress": (0, 100), "resp_rate": (4, 60), "body_temp": (30, 43)}
CUMULATIVE = {"steps", "active_kcal", "sleep_min"}

_lock = threading.Lock()
_hits = []

TOOLS = [
    tool("get_health_metrics",
         "Read his body data from the paired wearable/phone health app: heart_rate, resting_hr, hrv, spo2, "
         "steps, sleep_min, weight_kg, active_kcal, stress. Returns per-day summaries. Report numbers "
         "plainly; never diagnose -- for anything worrying, suggest checking with a doctor.",
         {"metric": S, "days": I}, []),
]
NAMES = {"get_health_metrics"}
KEYWORDS = ("heart rate", "heartrate", "pulse", "sleep", "slept", "steps", "walked", "spo2", "oxygen",
            "hrv", "weight", "calories", "watch", "wearable", "fitness", "health data", "stress level")


def _db():
    c = sqlite3.connect(DB, timeout=10)
    c.execute("create table if not exists samples (metric text, value real, at real, source text)")
    c.execute("create index if not exists ix_m_at on samples(metric, at)")
    c.execute("create unique index if not exists ux_sample on samples(metric, at, source)")
    return c


def init(**deps):
    try:
        with _lock:
            _db().close()
    except Exception as e:
        print(f"[telemetry] db init failed: {e}", flush=True)


def _ts(v):
    if v is None:
        return time.time()
    if isinstance(v, (int, float)):
        return v / 1000.0 if v > 1e12 else float(v)
    s = str(v).strip().replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            d = _dt.datetime.fromisoformat(s) if fmt is None else _dt.datetime.strptime(s, fmt)
            if d.tzinfo is None:
                d = d.replace(tzinfo=IST)
            return d.timestamp()
        except Exception:
            continue
    return time.time()


def _norm(name, value, unit=""):
    m = ALIASES.get(str(name or "").strip().lower().replace(" ", "_").replace("-", "_"))
    if not m:
        return None
    try:
        v = float(value)
    except Exception:
        return None
    u = (unit or "").lower()
    if m == "sleep_min" and u in ("hr", "h", "hours"):
        v *= 60
    if m == "spo2" and v <= 1.0:
        v *= 100
    if m == "weight_kg" and u in ("lb", "lbs"):
        v *= 0.4536
    lo, hi = RANGES[m]
    return (m, v) if lo <= v <= hi else None


def parse(payload):
    """Accepts several common shapes; returns [(metric, value, at, source)]."""
    out = []
    src = str((payload or {}).get("source", "ingest"))[:40] if isinstance(payload, dict) else "ingest"
    if isinstance(payload, dict) and isinstance(payload.get("metrics"), list):
        for s in payload["metrics"]:
            n = _norm(s.get("type") or s.get("metric") or s.get("name"), s.get("value", s.get("qty")), s.get("unit", ""))
            if n:
                out.append((n[0], n[1], _ts(s.get("at") or s.get("timestamp") or s.get("date")), src))
    elif isinstance(payload, dict) and isinstance((payload.get("data") or {}).get("metrics"), list):
        for m in payload["data"]["metrics"]:            # Health Auto Export shape
            for p in m.get("data") or []:
                val = p.get("qty", p.get("Avg", p.get("asleep", p.get("totalSleep"))))
                n = _norm(m.get("name"), val, m.get("units", ""))
                if n:
                    out.append((n[0], n[1], _ts(p.get("date") or p.get("sleepEnd")), "health-auto-export"))
    elif isinstance(payload, dict):
        at = _ts(payload.get("at") or payload.get("timestamp"))
        for k, v in payload.items():
            n = _norm(k, v) if not isinstance(v, (dict, list)) else None
            if n:
                out.append((n[0], n[1], at, src))
    return out[:MAX_SAMPLES]


def store(samples):
    if not samples:
        return 0
    with _lock:
        c = _db()
        try:
            n0 = c.total_changes
            c.executemany("insert or ignore into samples(metric, value, at, source) values (?,?,?,?)", samples)
            c.commit()
            return c.total_changes - n0
        finally:
            c.close()


def _token_ok(h):
    want = os.environ.get("TELEMETRY_TOKEN_SHA256", "")
    got = (h.headers.get("Authorization") or "")
    if not want or not got.startswith("Bearer "):
        return False
    return hmac.compare_digest(hashlib.sha256(got[7:].strip().encode()).hexdigest(), want)


def handle(h, data, is_owner):
    """POST /telemetry/ingest -- wired from do_POST (not in _PROTECTED_POST: it has its own auth)."""
    if not flag("TELEMETRY"):
        return h._json(503, {"error": "telemetry disabled"})
    if not (is_owner or _token_ok(h)):
        return h._json(401, {"error": "unauthorized"})
    now = time.time()
    with _lock:
        _hits[:] = [t for t in _hits if now - t < 60]
        if len(_hits) >= RATE_PER_MIN:
            return h._json(429, {"error": "rate limited"})
        _hits.append(now)
    samples = parse(data)
    added = store(samples)
    return h._json(200, {"ok": True, "received": len(samples), "stored": added})


# ---------------- reading ----------------
def _rows(metric, since):
    with _lock:
        c = _db()
        try:
            return c.execute("select value, at from samples where metric=? and at>=? order by at", (metric, since)).fetchall()
        finally:
            c.close()


def _daily(metric, days):
    rows = _rows(metric, time.time() - days * 86400)
    by = {}
    for v, at in rows:
        by.setdefault(_dt.datetime.fromtimestamp(at, IST).date().isoformat(), []).append(v)
    return by


def summary(metric="", days=7):
    days = max(1, min(int(days or 7), 90))
    metrics = [ALIASES.get(metric.lower().replace(" ", "_"), metric)] if metric else list(RANGES)
    lines = []
    for m in metrics:
        if m not in RANGES:
            continue
        by = _daily(m, days)
        if not by:
            continue
        parts = []
        for d in sorted(by)[-days:]:
            vs = by[d]
            if m in CUMULATIVE:
                parts.append(f"{d[5:]}: {max(vs) if m != 'sleep_min' else sum(vs):.0f}")
            else:
                parts.append(f"{d[5:]}: avg {sum(vs)/len(vs):.0f} (min {min(vs):.0f}, max {max(vs):.0f})")
        lines.append(f"{m}: " + "; ".join(parts))
    if not lines:
        return ("No wearable data has arrived yet. Pair a phone health app to post to "
                "/telemetry/ingest (see the setup note) and I'll start tracking.")
    return "From his paired health data (not a diagnosis):\n" + "\n".join(lines)


def signals():
    """Gentle, non-diagnostic observations for ambient autonomy."""
    if not flag("TELEMETRY"):
        return []
    out = []
    try:
        base = [v for v, _ in _rows("resting_hr", time.time() - 30 * 86400)]
        recent = [v for v, at in _rows("resting_hr", time.time() - 3 * 86400)]
        if len(base) >= 10 and len(recent) >= 2:
            b, r = sum(base) / len(base), sum(recent) / len(recent)
            if r - b >= 10:
                out.append(f"His resting heart rate the last 3 days ({r:.0f}) is about {r-b:.0f} above his usual ({b:.0f}).")
        sleep = _daily("sleep_min", 2)
        y = (_dt.datetime.now(IST).date()).isoformat()
        if y in sleep and sum(sleep[y]) < 300:
            out.append(f"He slept only about {sum(sleep[y])/60:.1f} hours last night.")
        now = _dt.datetime.now(IST)
        st = _daily("steps", 1).get(now.date().isoformat())
        if st and now.hour >= 18 and max(st) < 2000:
            out.append(f"Only about {max(st):.0f} steps so far today.")
    except Exception:
        pass
    return out


def call(name, args):
    try:
        if not flag("TELEMETRY"):
            return {"status": "error", "error": "telemetry is switched off"}
        if name == "get_health_metrics":
            a = args or {}
            return {"status": "success", "output": summary(a.get("metric", ""), a.get("days", 7))}
        return {"status": "error", "error": f"unknown tool {name}"}
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
