"""Client for Layla's agent gateway (the ONLY way an agent reaches her tools).

Each agent authenticates with its own token (env L365_GW_TOKEN_<AGENT>, loaded
from /opt/layla365/secrets/gateway.env). Layla enforces what is allowed; this
client never raises -- a failure is returned as (code, {"error": ...}).
"""
import json
import os
import urllib.error
import urllib.request

URL = os.environ.get("L365_GATEWAY_URL", "https://layla.tryvanta.in/agent/gateway")


def call(agent: str, body: dict, timeout: int = 45):
    req = urllib.request.Request(
        URL, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "l365/1.0",
                 "X-L365-Agent": agent, "X-L365-Token": os.environ.get("L365_GW_TOKEN_" + agent.upper(), "")})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:  # noqa: BLE001
            return e.code, {"error": f"http {e.code}"}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": f"{type(e).__name__}"}


def heartbeat(agent, info=None):
    return call(agent, {"verb": "heartbeat", "info": info or {}}, timeout=15)


def inbox(agent):
    return call(agent, {"verb": "inbox"}, timeout=20)


def report(agent, kind, title, body, severity="info", tg_body=None):
    payload = {"verb": "report", "kind": kind, "title": title[:120], "body": body[:4000], "severity": severity}
    try:  # also surface to the owner's Telegram (digest or instant alert); never blocks the report
        from . import telegram
        telegram.collect(agent, kind, title, body if tg_body is None else tg_body, severity)
    except Exception:  # noqa: BLE001
        pass
    code, out = call(agent, payload)
    if _retryable(code):
        _enqueue(agent, payload)
    return code, out


def task_done(agent, tid, ok, result):
    payload = {"verb": "task_done", "id": tid, "ok": ok, "result": result[:600]}
    code, out = call(agent, payload, timeout=20)
    if _retryable(code):
        _enqueue(agent, payload)
    return code, out


# ---------------- retry queue (outbox) ----------------
# If Layla (Oracle) is down or unreachable, reports and task results are kept on disk and re-sent on
# later ticks instead of being lost. Only transport/server failures are queued (never 4xx: those are
# refusals that would fail again). Items older than OUTBOX_MAX_AGE_S are dropped; a delayed report says
# when it was originally written.
import fcntl
import threading
import time

OUTBOX = os.environ.get("L365_OUTBOX", "/opt/layla365/state/outbox.jsonl")
OUTBOX_MAX_AGE_S = 3 * 86400
OUTBOX_MAX_ITEMS = 2000
_olock = threading.Lock()


def _retryable(code):
    return code == 0 or code >= 500 or code == 429


def _enqueue(agent, payload):
    rec = {"agent": agent, "payload": payload, "queued_at": time.time(), "tries": 0}
    try:
        os.makedirs(os.path.dirname(OUTBOX), exist_ok=True)
        with _olock, open(OUTBOX, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"[outbox] queued {payload.get('verb')} from {agent} (Layla unreachable)", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[outbox] could not queue: {type(e).__name__}", flush=True)


def outbox_size():
    try:
        with open(OUTBOX, encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
    except FileNotFoundError:
        return 0


def flush_outbox(max_send=25):
    """Re-send queued items, oldest first. Stops at the first transport failure (Layla still down)."""
    if not os.path.exists(OUTBOX):
        return 0
    with _olock:
        with open(OUTBOX, "r+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            items = []
            for line in f:
                try:
                    items.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    pass
            now, sent, keep, down = time.time(), 0, [], False
            for it in items:
                if now - it.get("queued_at", now) > OUTBOX_MAX_AGE_S:
                    continue                                   # too old to matter
                if down or sent >= max_send:
                    keep.append(it); continue
                p = dict(it["payload"])
                if p.get("verb") == "report":
                    when = time.strftime("%d %b %H:%M", time.localtime(it["queued_at"]))
                    p["body"] = (p.get("body", "") + f" (delayed report, written {when})")[:4000]
                code, _ = call(it["agent"], p, timeout=20)
                if _retryable(code):
                    it["tries"] = it.get("tries", 0) + 1
                    keep.append(it); down = True
                else:
                    sent += 1
            keep = keep[-OUTBOX_MAX_ITEMS:]
            f.seek(0); f.truncate()
            for it in keep:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
    if sent:
        print(f"[outbox] delivered {sent} delayed item(s); {len(keep)} still queued", flush=True)
    return sent


def request(agent, action, args):
    return call(agent, {"verb": "request", "action": action, "args": args or {}})
