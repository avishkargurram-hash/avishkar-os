"""Naina's external site monitor (#6): HTTP status, latency and TLS expiry for the owner's public domains.

Black-box only: plain HTTPS requests from the VPS, no logins, no SSH, no server access of any kind.
Deterministic (no LLM). State lives in a small JSON file so a restart never re-alerts or forgets an outage.

Alert rules (kept deliberately quiet):
  * DOWN      -- 2 consecutive failed checks (connection error, timeout, or HTTP >= 500). Re-reminded every 6 h.
  * RECOVERED -- first good check after a DOWN alert.
  * TLS       -- certificate expires in < 14 days (warn) / < 5 days (critical); at most once a day per domain.
  * SLOW      -- 3 consecutive checks above 5 s; at most once a day per domain.
A 4xx answer (login wall, 404 on "/") counts as UP: the server is answering.
"""
import json
import os
import socket
import ssl
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

STATE = os.environ.get("L365_SITEMON", "/opt/layla365/state/sitemon.json")
TARGETS = [
    "music.tryvanta.in", "learn.music.tryvanta.in", "teach.music.tryvanta.in", "mcam.music.tryvanta.in",
    "growth.music.tryvanta.in", "jenni.music.tryvanta.in",
    "coed.tryvanta.in", "bro.tryvanta.in", "coupler.tryvanta.in", "layla.tryvanta.in", "jobsignal.tryvanta.in",
    "mavito.tryvanta.in", "hago.tryvanta.in",
    "tryvanta.in", "tryvanta.in/social",
    "humanify.space", "krupaclinic.com", "southindiajournal.com", "muzicllyglobal.com", "avishkarroopi.tech",
]
TIMEOUT = 12
DOWN_AFTER, REMIND_H, SLOW_S, SLOW_AFTER = 2, 6, 5.0, 3
TLS_WARN_D, TLS_CRIT_D = 14, 5
KEEP_DAYS = 8
UA = "Layla365-SiteMonitor/1.0 (+owner monitoring)"


def _now():
    return datetime.now(timezone.utc)


def _load():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"sites": {}}


def _save(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f)
    os.replace(tmp, STATE)


def tls_days_left(host, port=443):
    """Days until the served certificate expires (None if it cannot be read). Validates the chain too."""
    ctx = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=TIMEOUT) as s:
        with ctx.wrap_socket(s, server_hostname=host) as t:
            exp = ssl.cert_time_to_seconds(t.getpeercert()["notAfter"])
    return (exp - time.time()) / 86400.0


def check(target):
    """One probe -> {ok, code, ms, tls_days, err}. Never raises."""
    host = target.split("/")[0]
    url = "https://" + target + ("/" if "/" not in target else "")
    r = {"ok": False, "code": None, "ms": None, "tls_days": None, "err": None}
    t0 = time.monotonic()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                resp.read(2048)
                r["code"] = resp.status
        except urllib.error.HTTPError as e:   # 4xx/5xx still means the server answered
            r["code"] = e.code
        r["ms"] = round((time.monotonic() - t0) * 1000)
        r["ok"] = r["code"] is not None and r["code"] < 500
    except ssl.SSLError as e:
        r["err"] = "tls: " + str(e)[:80]
    except Exception as e:  # noqa: BLE001
        r["err"] = (type(e).__name__ + ": " + str(getattr(e, "reason", e)))[:90]
    try:
        r["tls_days"] = round(tls_days_left(host), 1)
    except Exception:  # noqa: BLE001
        pass
    return r


def run(targets=None, probe=check, now=None):
    """Probe every target, update state, return (summary_rows, alerts). alerts = [(severity, title, body)]."""
    now = now or _now()
    st = _load()
    sites = st.setdefault("sites", {})
    targets = targets or TARGETS
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(probe, targets))
    alerts, rows = [], []
    day = now.strftime("%Y-%m-%d")
    for tgt, r in zip(targets, results):
        s = sites.setdefault(tgt, {"fails": 0, "slow": 0, "down": False, "last_alert": {}, "days": {}})
        d = s["days"].setdefault(day, {"n": 0, "ok": 0, "ms": []})
        d["n"] += 1
        d["ok"] += 1 if r["ok"] else 0
        if r["ms"] is not None:
            d["ms"] = (d["ms"] + [r["ms"]])[-300:]
        s["days"] = {k: v for k, v in s["days"].items()
                     if k >= (now - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")}
        s["last"] = {"ts": now.isoformat(timespec="seconds"), **r}

        def due(kind, hours):
            ts = s["last_alert"].get(kind)
            return ts is None or now - datetime.fromisoformat(ts) >= timedelta(hours=hours)

        def mark(kind):
            s["last_alert"][kind] = now.isoformat(timespec="seconds")

        if r["ok"]:
            s["ever_ok"], s["not_live"] = True, False
            if s["down"]:
                alerts.append(("info", f"{tgt} is back up", f"{tgt} is answering again (HTTP {r['code']}, {r['ms']} ms)."))
                s["down"] = False
                s["last_alert"].pop("down", None)
            s["fails"] = 0
        elif "Name or service not known" in (r["err"] or "") and not s.get("ever_ok"):
            s["not_live"] = True          # DNS record never existed: not deployed yet, nothing to alert on
            s["fails"] = 0
        else:
            s["fails"] += 1
            why = r["err"] or f"HTTP {r['code']}"
            if s["fails"] >= DOWN_AFTER and (not s["down"] or due("down", REMIND_H)):
                alerts.append(("critical", f"{tgt} is DOWN",
                               f"{tgt} failed {s['fails']} checks in a row ({why}). Checked from the agents server over HTTPS."))
                s["down"] = True
                mark("down")
        if r["ok"] and r["ms"] is not None and r["ms"] / 1000.0 > SLOW_S:
            s["slow"] += 1
            if s["slow"] >= SLOW_AFTER and due("slow", 24):
                alerts.append(("warn", f"{tgt} is slow", f"{tgt} took {r['ms']} ms (over {SLOW_S:.0f}s) for {s['slow']} checks in a row."))
                mark("slow")
        else:
            s["slow"] = 0
        td = r["tls_days"]
        if td is not None and td < TLS_WARN_D and due("tls", 24):
            sev = "critical" if td < TLS_CRIT_D else "warn"
            alerts.append((sev, f"{tgt}: TLS certificate expires in {int(td)} days",
                           f"The HTTPS certificate for {tgt.split('/')[0]} expires in about {int(td)} days. Renew it (certbot renew / panel)."))
            mark("tls")
        rows.append((tgt, r))
    _save(st)
    return rows, alerts


def daily_summary(now=None):
    """Plain-text uptime/latency lines for the last 24 h bucket (today in IST-agnostic UTC days) from state."""
    st = _load()
    now = now or _now()
    out, bad = [], 0
    for tgt in TARGETS:
        s = st.get("sites", {}).get(tgt)
        if not s:
            continue
        n = ok = 0
        ms = []
        for k in (now.strftime("%Y-%m-%d"), (now - timedelta(days=1)).strftime("%Y-%m-%d")):
            d = s["days"].get(k)
            if d:
                n += d["n"]; ok += d["ok"]; ms += d["ms"]
        if s.get("not_live"):
            out.append(f"{tgt}: no DNS record yet (not deployed), not monitored")
            continue
        if not n:
            continue
        up = 100.0 * ok / n
        p50 = sorted(ms)[len(ms) // 2] if ms else None
        tls = (s.get("last") or {}).get("tls_days")
        flag = "" if up >= 99.0 else "  <-- check"
        bad += 1 if flag else 0
        out.append(f"{tgt}: {up:.1f}% up, median {p50} ms, TLS {int(tls) if tls is not None else '?'} d{flag}")
    return out, bad
