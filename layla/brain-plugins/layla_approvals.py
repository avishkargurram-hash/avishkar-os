"""Owner approvals -- shared by computer-use (#10) and social agency (#11).

Anything that acts OUTSIDE Layla (controls the PC, messages another person)
waits here for an explicit owner decision. The page shows an Allow/Deny card
(SSE event "approval"); the owner can also answer by voice through the
answer_pending_approval tool. Pending requests expire (default 10 min) and are
NOT carried across a restart -- an expired request can never be approved late.
"""
import threading
import time
import uuid

from layla_plugin_util import S, tool

_D = {}            # push
_pending = {}      # id -> {kind, title, detail, created, expires, cb}
_lock = threading.Lock()

TOOLS = [tool("answer_pending_approval",
              "Pass on the owner's spoken yes/no to the approval request that is currently waiting "
              "(PC control or a message to someone). Only call this when HE clearly said yes/allow/go ahead "
              "or no/deny/cancel in reply to that request -- never decide for him.",
              {"decision": {"type": "string", "enum": ["allow", "deny"]}, "id": S}, ["decision"])]
NAMES = {"answer_pending_approval"}
KEYWORDS = ("allow it", "approve", "go ahead", "deny", "don't send", "dont send", "send it", "yes send",
            "cancel that", "allow", "approved")


def init(**deps):
    _D.update(deps)


def request(kind, title, detail, cb, ttl=600):
    aid = uuid.uuid4().hex[:10]
    with _lock:
        _pending[aid] = {"kind": kind, "title": title, "detail": detail, "created": time.time(),
                         "expires": time.time() + ttl, "cb": cb}
    try:
        _D["push"]({"type": "approval", "id": aid, "kind": kind, "title": title, "detail": detail,
                    "expires_in": ttl})
    except Exception:
        pass
    return aid


def _expire():
    now = time.time()
    with _lock:
        for k in [k for k, v in _pending.items() if v["expires"] < now]:
            v = _pending.pop(k)
            try:
                v["cb"](False, "expired")
            except Exception:
                pass


def decide(aid, allow, via="card"):
    _expire()
    with _lock:
        if not aid and _pending:
            aid = max(_pending, key=lambda k: _pending[k]["created"])
        p = _pending.pop(aid, None)
    if p is None:
        return {"ok": False, "error": "no such pending request (it may have expired)"}
    try:
        _D["push"]({"type": "approval_closed", "id": aid, "allowed": bool(allow)})
    except Exception:
        pass
    try:
        out = p["cb"](bool(allow), via)
    except Exception as e:
        out = f"error: {type(e).__name__}"
    return {"ok": True, "id": aid, "allowed": bool(allow), "result": out}


def pending_list():
    _expire()
    with _lock:
        return [{"id": k, "kind": v["kind"], "title": v["title"], "detail": v["detail"],
                 "expires_in": int(v["expires"] - time.time())} for k, v in _pending.items()]


def call(name, args):
    try:
        args = args or {}
        if name == "answer_pending_approval":
            if not pending_list():
                return {"status": "success", "output": "There is nothing waiting for approval right now."}
            r = decide(args.get("id") or "", str(args.get("decision", "")).lower() == "allow", via="voice")
            if not r["ok"]:
                return {"status": "success", "output": r["error"]}
            return {"status": "success", "output": f"{'Approved' if r['allowed'] else 'Denied'}. {r['result'] or ''}".strip()}
        return {"status": "error", "error": f"unknown tool {name}"}
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
