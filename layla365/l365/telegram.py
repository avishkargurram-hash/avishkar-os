"""Telegram bridge for Layla 365 -- the owner's window into his agents.

The runner collects every report into a per-hour buffer and sends ONE combined digest to the owner, only
when something happened, and only in his waking window (14:00-05:00 IST; silent 05:00-14:00). Alerts and
invention success/milestone reports go instantly (also silenced in quiet hours -- owner's choice). Approval
requests (e.g. Naina wanting to write) are sent instantly with inline Allow/Deny buttons; the owner's tap or
his typed "approve <id>" / "reject <id>" is read back via getUpdates and resolved.

Only the owner's chat_id (OWNER_CHAT_ID) may command the bot. Token + chat_id live in secrets, never logged.
Kill switch: TELEGRAM_AGENTS=0. Never raises into the caller.
"""
import datetime as _dt
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
TOKEN = os.environ.get("TELEGRAM_AGENTS_TOKEN", "")
OWNER = os.environ.get("TELEGRAM_OWNER_CHAT_ID", "")
QUIET_START, QUIET_END = 5, 14          # IST hours with no messages at all
API = "https://api.telegram.org/bot"

_buf = []                                # pending digest items
_lock = threading.Lock()
_offset = [0]                            # getUpdates cursor
# approval callbacks: id -> {"cb": fn(allowed), "summary": str, "at": ts, "done": bool}
_approvals = {}


def enabled():
    return bool(TOKEN) and bool(OWNER) and os.environ.get("TELEGRAM_AGENTS", "1") != "0"


def quiet_now():
    return QUIET_START <= _dt.datetime.now(IST).hour < QUIET_END


def _api(method, params, timeout=20):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(API + TOKEN + "/" + method, data=data, headers={"User-Agent": "l365tg/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _send(text, buttons=None, force=False):
    """force=True bypasses quiet hours (not used today -- owner wants full quiet). Never raises."""
    if not enabled() or (quiet_now() and not force):
        return False
    try:
        p = {"chat_id": OWNER, "text": text[:4000], "parse_mode": "HTML", "disable_web_page_preview": "true"}
        if buttons:
            p["reply_markup"] = json.dumps({"inline_keyboard": buttons})
        return bool(_api("sendMessage", p).get("ok"))
    except Exception as e:  # noqa: BLE001
        print(f"[telegram] send failed: {type(e).__name__}", flush=True)
        return False


def _esc(s):
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------- collection (called from the gateway's report path, best-effort) ----------------
def collect(agent, kind, title, body, severity):
    if not enabled():
        return
    if kind == "alert" or severity in ("warn", "critical") or kind == "milestone":
        emoji = "\U0001F6A8" if severity == "critical" else "⚠️" if severity == "warn" else "\U0001F4A1"
        notify(f"{emoji} <b>{_esc(agent.capitalize())}</b>: {_esc(title)}\n{_esc(body)[:600]}")
        return
    with _lock:
        _buf.append({"agent": agent, "title": title, "body": body, "at": time.time()})


def notify(text, buttons=None):
    """Instant message (alerts, milestones). Silent in quiet hours."""
    threading.Thread(target=_send, args=(text, buttons), daemon=True).start()


def send_digest():
    """Called hourly by the runner. Sends one combined message if anything is buffered and not quiet."""
    if not enabled() or quiet_now():
        return 0
    with _lock:
        items, _buf[:] = list(_buf), []
    if not items:
        return 0
    by = {}
    for it in items:
        by.setdefault(it["agent"], []).append(it)
    now = _dt.datetime.now(IST).strftime("%d %b, %I:%M %p")
    lines = [f"\U0001F550 <b>Agents update</b> — {now}"]
    for agent in sorted(by):
        lines.append(f"\n<b>{_esc(agent.capitalize())}</b>")
        for it in by[agent][-3:]:
            lines.append(f"• {_esc(it['title'])}: {_esc(it['body'])[:220]}")
    _send("\n".join(lines))
    return len(items)


# ---------------- approvals (Naina write, etc.) ----------------
def request_approval(summary, detail, cb, ttl=24 * 3600, aid=None, send=True):
    """Send an Allow/Deny card; cb(allowed: bool) runs when the owner decides. Returns the approval id."""
    aid = aid or "ap" + str(int(time.time() * 1000))[-9:]
    with _lock:
        _approvals[aid] = {"cb": cb, "summary": summary, "at": time.time(), "ttl": ttl, "done": False}
    text = f"\U0001F510 <b>Approval needed</b>\n{_esc(summary)}\n\n{_esc(detail)[:1500]}\n\n<i>id {aid}</i>"
    buttons = [[{"text": "✅ Allow", "callback_data": f"ap:{aid}:1"},
                {"text": "❌ Deny", "callback_data": f"ap:{aid}:0"}]]
    # approvals bypass quiet hours? Owner said no alerts in quiet hours; an approval can wait, so respect quiet.
    if send:
        if quiet_now():   # owner wants silence 05:00-14:00: hold the card, poll() sends it when quiet ends
            with _lock:
                _approvals[aid]["unsent"] = (text, buttons)
        else:
            threading.Thread(target=_send, args=(text, buttons), daemon=True).start()
    return aid


def _resolve(aid, allowed, via):
    with _lock:
        a = _approvals.get(aid)
        if not a or a["done"]:
            return False
        a["done"] = True
    try:
        a["cb"](bool(allowed))
    except Exception as e:  # noqa: BLE001
        print(f"[telegram] approval cb failed: {type(e).__name__}", flush=True)
    tag = "✅ Allowed" if allowed else "❌ Denied"
    _send(tag + ": " + _esc(a["summary"]) + " <i>(via " + via + ")</i>", force=True)
    return True


def pending_approvals():
    now = time.time()
    with _lock:
        for aid in [k for k, v in _approvals.items() if not v["done"] and now - v["at"] > v["ttl"]]:
            _approvals[aid]["done"] = True
            try:
                _approvals[aid]["cb"](False)
            except Exception:  # noqa: BLE001
                pass
        return [(k, v["summary"]) for k, v in _approvals.items() if not v["done"]]


# ---------------- RSI approval relay (Layla self-modification gate) ----------------
def _resolve_rsi(proposal_id, allowed):
    """Owner tapped Allow/Deny on an RSI self-change card. Relay the decision to the Scientist API,
    which holds the real secret and performs the backup+apply+rollback. Never raises."""
    api = os.environ.get("SCIENTIST_RSI_URL", "http://127.0.0.1:8095").rstrip("/")
    bearer = os.environ.get("SCIENTIST_API_TOKEN", "")
    secret = os.environ.get("RSI_AUTH_SECRET", "")
    if not secret:
        _send("RSI gate is not armed on the server (RSI_AUTH_SECRET unset); decision ignored.", force=True)
        return
    body = json.dumps({"proposal_id": proposal_id, "decision": "APPROVE" if allowed else "REJECT",
                       "auth_token": secret}).encode()
    try:
        req = urllib.request.Request(f"{api}/api/rsi/decide", data=body,
                                     headers={"Content-Type": "application/json",
                                              "Authorization": f"Bearer {bearer}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = json.loads(r.read())
        msg = resp.get("message") or resp.get("detail") or resp.get("error") or str(resp)
    except Exception as e:  # noqa: BLE001
        msg = f"relay to Scientist API failed: {type(e).__name__}: {e}"
    tag = "✅ Allowed" if allowed else "❌ Denied"
    _send(f"{tag} RSI {_esc(proposal_id)}: {_esc(str(msg)[:600])}", force=True)


# ---------------- incoming (polled by the runner) ----------------
def poll():
    """Read the owner's taps and typed commands. Never raises. Called every tick."""
    if not enabled():
        return
    if not quiet_now():
        with _lock:
            held = [(k, v["unsent"]) for k, v in _approvals.items() if v.get("unsent") and not v["done"]]
            for k, _ in held:
                _approvals[k]["unsent"] = None
        for _, (text, buttons) in held:
            _send(text, buttons)
    try:
        out = _api("getUpdates", {"offset": _offset[0] + 1, "timeout": 0, "limit": 20}, timeout=25)
    except Exception:  # noqa: BLE001
        return
    for u in out.get("result", []):
        _offset[0] = max(_offset[0], u["update_id"])
        cq = u.get("callback_query")
        if cq:
            frm = str((cq.get("from") or {}).get("id"))
            data = cq.get("data", "")
            if frm == OWNER and data.startswith("ap:"):
                _, aid, val = data.split(":", 2)
                _resolve(aid, val == "1", "button")
            elif frm == OWNER and data.startswith("rsi:"):
                _, pid, val = data.split(":", 2)
                _resolve_rsi(pid, val == "1")
            try:
                _api("answerCallbackQuery", {"callback_query_id": cq["id"]})
            except Exception:  # noqa: BLE001
                pass
            continue
        msg = u.get("message") or {}
        if str((msg.get("chat") or {}).get("id")) != OWNER:
            continue
        text = (msg.get("text") or "").strip()
        low = text.lower()
        if low in ("/start", "/help"):
            _send("I'm your agents' bot. You'll get an hourly update (2 PM–5 AM) and approval buttons here. "
                  "Reply <code>approve &lt;id&gt;</code> or <code>reject &lt;id&gt;</code>, or <code>/status</code>.", force=True)
        elif low == "/status":
            p = pending_approvals()
            _send("Pending approvals: " + (", ".join(a for a, _ in p) if p else "none") + ".", force=True)
        elif low.startswith(("approve ", "reject ")):
            verb, aid = low.split(None, 1)
            if not _resolve(aid.strip(), verb == "approve", "text"):
                _send(f"No pending approval with id {_esc(aid.strip())}.", force=True)
