"""Layla social agency -- Task 1, capability #11 (asynchronous external social agency).

She can now work with OTHER people on his behalf, asynchronously:
  draft -> HIS approval -> send -> (optionally) watch for their reply -> report back.

* Every outgoing message to another person goes through layla_approvals
  (Allow/Deny card or a spoken yes). HARD RULE from Task 2: no external
  message is ever sent without his explicit approval -- there is no
  auto-send path in this module. WhatsApp/SMS additionally still need his
  tap on the phone (existing phone-agent gate); email still uses the
  existing stage -> confirm path.
* ask_and_report: "ask Ravi if the documents are ready and tell me what he
  says" -> drafted, approved, sent, then the reply is looked for in his
  phone notifications/SMS and summarised back to him (SSE notify).
* Social posts (X/LinkedIn/Instagram): no posting API is connected, so she
  drafts the post and keeps it ready -- she never pretends she posted.

Kill switch: SOCIAL=0. Never raises into the caller.
"""
import re
import threading
import time
import uuid

from layla_plugin_util import B, S, flag, fmt_ts, llm_json, tool

OUTBOX_KEY = "social:outbox"
CHANNELS = ("whatsapp", "sms", "email", "post")
REPLY_POLL_S = 600
DEFAULT_WAIT_H = 24

_D = {}   # memory, execute_tool, approvals, push, log_said
_lock = threading.Lock()

TOOLS = [
    tool("draft_message",
         "Prepare a message to ANOTHER person (WhatsApp, SMS or email) or a social-media post. It is NOT "
         "sent: he gets an Allow/Deny card and can also say yes or no. Use this for every message to "
         "someone else. Write the text the way he would, short and natural.",
         {"channel": {"type": "string", "enum": list(CHANNELS)}, "to": S, "text": S, "subject": S,
          "expect_reply": B}, ["channel", "to", "text"]),
    tool("ask_and_report",
         "Ask someone a question on his behalf and report their answer back to him when it arrives "
         "('ask Ravi if the documents are ready and tell me what he says'). Drafts the message for his "
         "approval, then watches for the reply for up to `wait_hours` (default 24).",
         {"channel": {"type": "string", "enum": ["whatsapp", "sms", "email"]}, "to": S, "question": S,
          "wait_hours": {"type": "integer"}}, ["to", "question"]),
    tool("list_outbox", "List messages/posts you drafted for him and their status (waiting for approval, "
                        "sent, waiting for reply, replied, cancelled).", {}, []),
    tool("cancel_outbox_item", "Cancel a drafted message or stop waiting for a reply.", {"id": S}, ["id"]),
]
NAMES = {t["function"]["name"] for t in TOOLS}
KEYWORDS = ("message", "text him", "text her", "whatsapp", "sms", "email", "mail", "tell him", "tell her",
            "ask him", "ask her", "let him know", "let her know", "post on", "tweet", "linkedin",
            "instagram", "outbox", "reply", "replied", "draft")


def init(**deps):
    _D.update(deps)


def _load():
    return _D["memory"].recall("long_term", OUTBOX_KEY) or []


def _save(items):
    _D["memory"].remember("long_term", OUTBOX_KEY, items[-200:])


def _update(oid, **kv):
    with _lock:
        items = _load()
        for it in items:
            if it["id"] == oid:
                it.update(kv)
        _save(items)


def _get(oid):
    return next((i for i in _load() if i["id"] == oid), None)


def _dispatch(it):
    ex = _D["execute_tool"]
    ch = it["channel"]
    if ch == "whatsapp":
        return ex("phone_whatsapp", {"to": it["to"], "message": it["text"]})
    if ch == "sms":
        return ex("phone_sms", {"to": it["to"], "message": it["text"]})
    if ch == "email":
        staged = ex("send_email", {"to": it["to"], "subject": it.get("subject") or "(no subject)", "body": it["text"]})
        out = str(staged.get("output") or staged)
        m = re.search(r"pending[_ ]id[\"':= ]+([A-Za-z0-9_-]{4,})", out)
        if not m:
            return {"status": "error", "error": f"email could not be staged: {out[:160]}"}
        return ex("confirm_pending_action", {"pending_id": m.group(1)})
    if ch == "post":
        return {"status": "success", "output": "post ready -- no posting account is connected, so he posts it himself"}
    return {"status": "error", "error": f"unknown channel {ch}"}


def _on_decision(oid):
    def cb(allowed, via):
        it = _get(oid)
        if not it or it["status"] != "awaiting_approval":
            return "already handled"
        if not allowed:
            _update(oid, status="cancelled", decided_via=via)
            return "Okay, I won't send it."
        _update(oid, status="sending", decided_via=via)
        try:
            r = _dispatch(it)
        except Exception as e:
            r = {"status": "error", "error": f"{type(e).__name__}"}
        ok = r.get("status") == "success"
        status = ("waiting_reply" if it.get("expect_reply") else "sent") if ok else "failed"
        if it["channel"] == "post" and ok:
            status = "ready_to_post"
        _update(oid, status=status, sent_at=time.time(), result=str(r.get("output") or r.get("error"))[:300])
        msg = (f"Sent to {it['to']}." + (" I'll tell you when they reply." if it.get("expect_reply") else "")) if ok \
            else f"Couldn't send to {it['to']}: {str(r.get('error') or r.get('output'))[:120]}"
        if it["channel"] == "post" and ok:
            msg = "The post is ready for you to publish -- I don't have a posting account connected."
        if via == "card":
            try:
                _D["push"]({"type": "notify", "text": msg, "tone": "calm"})
            except Exception:
                pass
        return msg
    return cb


def draft(channel, to, text, subject="", expect_reply=False, question="", wait_hours=DEFAULT_WAIT_H):
    if not flag("SOCIAL"):
        return "Messaging other people is switched off right now."
    channel = (channel or "whatsapp").lower()
    if channel not in CHANNELS:
        return f"I can draft for {', '.join(CHANNELS)} only."
    if not (to or "").strip() or not (text or "").strip():
        return "I need who it's for and what to say."
    oid = uuid.uuid4().hex[:8]
    it = {"id": oid, "channel": channel, "to": to.strip(), "text": text.strip(), "subject": subject or "",
          "expect_reply": bool(expect_reply), "question": question, "created": time.time(),
          "wait_until": time.time() + max(1, int(wait_hours or DEFAULT_WAIT_H)) * 3600,
          "status": "awaiting_approval"}
    with _lock:
        items = _load()
        items.append(it)
        _save(items)
    title = {"post": "Post this?", "email": f"Email {it['to']}?"}.get(channel, f"Send to {it['to']} on {channel}?")
    detail = (f"Subject: {subject}\n" if subject else "") + it["text"]
    aid = _D["approvals"].request("message", title, detail, _on_decision(oid))
    _update(oid, approval_id=aid)
    return (f"Drafted (id {oid}), NOT sent yet. Read it back to him in one line and ask if you should send it -- "
            f"he can also tap Allow on screen. Draft: \"{it['text']}\"")


# ---------------- async reply watching ----------------
_REPLY = """You read a phone's recent notifications/SMS. Find messages FROM the given person that arrived
AFTER the given time and answer the question that was asked to them. Return ONLY JSON:
{"found": true/false, "reply": "their reply in one or two plain sentences, or empty"}."""


def _check_replies():
    for it in [i for i in _load() if i["status"] == "waiting_reply"]:
        if time.time() > it["wait_until"]:
            _update(it["id"], status="no_reply")
            _say(f"No reply yet from {it['to']} to \"{it['text'][:60]}\". Want me to nudge them?")
            continue
        ex = _D["execute_tool"]
        dump = []
        for nm, a in (("phone_notifications", {"limit": 30, "app": "whatsapp" if it["channel"] == "whatsapp" else ""}),
                      ("phone_read_sms", {"limit": 15})):
            if it["channel"] == "email":
                break
            try:
                r = ex(nm, a)
                dump.append(str(r.get("output") or "")[:3000])
            except Exception:
                pass
        if it["channel"] == "email":
            try:
                r = ex("gmail_search", {"query": f"from:{it['to']} newer_than:2d", "max_results": 5})
                dump.append(str(r.get("output") or "")[:3000])
            except Exception:
                pass
        text = "\n".join(d for d in dump if d)
        first = it["to"].split()[0].lower()
        if not text or first not in text.lower():
            continue
        try:
            res = llm_json(_REPLY, f"PERSON: {it['to']}\nSENT AT: {fmt_ts(it.get('sent_at', it['created']))}\n"
                                   f"WHAT WAS ASKED: {it.get('question') or it['text']}\nINBOX:\n{text}", max_tokens=300)
        except Exception:
            continue
        if res.get("found") and res.get("reply"):
            _update(it["id"], status="replied", reply=res["reply"], replied_at=time.time())
            _say(f"{it['to']} replied: {res['reply']}")


def _say(text):
    try:
        _D["push"]({"type": "notify", "text": text, "tone": "warm"})
        if _D.get("log_said"):
            _D["log_said"](text)
    except Exception:
        pass


def _loop():
    time.sleep(90)
    while True:
        try:
            if flag("SOCIAL"):
                _check_replies()
        except Exception as e:
            print(f"[social] reply check failed: {type(e).__name__}", flush=True)
        time.sleep(REPLY_POLL_S)


def start():
    threading.Thread(target=_loop, daemon=True, name="social").start()


def call(name, args):
    args = args or {}
    try:
        if name == "draft_message":
            return {"status": "success", "output": draft(args.get("channel"), args.get("to"), args.get("text"),
                                                         args.get("subject", ""), args.get("expect_reply", False))}
        if name == "ask_and_report":
            q = (args.get("question") or "").strip()
            return {"status": "success", "output": draft(args.get("channel") or "whatsapp", args.get("to"), q,
                                                         expect_reply=True, question=q,
                                                         wait_hours=args.get("wait_hours") or DEFAULT_WAIT_H)}
        if name == "list_outbox":
            items = _load()[-12:]
            if not items:
                return {"status": "success", "output": "Nothing in the outbox."}
            return {"status": "success", "output": "; ".join(
                f"[{i['id']}] {i['channel']} to {i['to']}: {i['status']}" + (f" -- reply: {i['reply']}" if i.get("reply") else "")
                for i in reversed(items))}
        if name == "cancel_outbox_item":
            it = _get(args.get("id", ""))
            if not it:
                return {"status": "success", "output": "No such item."}
            if it["status"] in ("awaiting_approval", "waiting_reply"):
                if it["status"] == "awaiting_approval" and it.get("approval_id"):
                    _D["approvals"].decide(it["approval_id"], False, via="cancel")
                _update(it["id"], status="cancelled")
                return {"status": "success", "output": "Cancelled."}
            return {"status": "success", "output": f"It's already {it['status']}."}
        return {"status": "error", "error": f"unknown tool {name}"}
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
