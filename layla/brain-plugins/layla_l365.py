"""Layla 365 gateway + orchestration -- Task 2/3 (runs inside the Oracle brain).

Layla is the BOSS; the nine agents (tv-mum-01, local model only) never hold a
tool, a key or a session of hers. They talk to her through four verbs:

  report     "here is what I did / found"  (daily | alert | note)
  request    "Layla, please do <action>"   -> executed by HER tool layer, under
             HER policy, from a fixed action catalogue (not arbitrary tools)
  inbox      collect tasks Layla/owner assigned to me
  heartbeat  "I'm alive, mode=..., last tick ..."

Defence in depth: nginx -> source-IP allowlist -> per-agent bearer token (only a
sha256 is stored) -> per-agent action allowlist -> arg validation -> per-minute
and per-day rate limits -> JSONL audit of EVERY call. Kill switches: file
/opt/layla/l365_gateway.disabled (all), or pause_agent (one agent).
Payments: there is no payment action in the catalogue, so none can exist.

For Layla herself (her tools): assign_agent_task, agent_status, agent_reports,
pause_agent. Every morning 08:00 IST she compiles the agents' evening reports
into one briefing for the owner. Her thinking uses Cerebras; agents never do.
"""
import datetime as _dt
import hashlib
import hmac
import json
import os
import re
import threading
import time
import uuid

from layla_plugin_util import IST, I, S, flag, llm, now_ist, tool

CONF = "/opt/layla/l365_gateway.json"
KILL = "/opt/layla/l365_gateway.disabled"
LOG = "/opt/layla/l365_gateway.log"
STATE = "/opt/layla/l365_agent_state.json"          # paused set (separate from the token config)
REPORTS_KEY, TASKS_KEY, STATUS_KEY, BRIEF_KEY = "l365:reports", "l365:tasks", "l365:status", "l365:briefings"
AGENTS = ("naina", "megha", "veda", "priya", "nitya", "shruti", "lydia", "maya", "kavya")
ROLES = {"naina": "engineer", "megha": "researcher", "veda": "inventor", "priya": "doctor & life (owns Almanac)",
         "nitya": "home automation", "shruti": "music teacher", "lydia": "finance", "maya": "B2B outreach",
         "kavya": "brand & media"}
BRIEF_HOUR_IST = 14          # owner sleeps 05:00-14:00 IST; brief him when he's up
MAX_OUT = 4000

_D = {}            # memory, execute_tool, push
_lock = threading.Lock()
_hits = {}         # agent -> [timestamps] (minute window)
_day = {}          # agent -> (date, count)
_alerts = {}       # agent -> [timestamps] (hour window)
_cache = {"mt": None, "conf": {}, "smt": None, "state": {}}

# ---- the action catalogue: name -> (brain tool, {arg: (type, required, enum/maxlen)}) ----
ACTIONS = {
    "web.search":        ("web_search", {"query": ("str", True, 300)}),
    "memory.recall":     ("recall_similar_facts", {"query": ("str", True, 300)}),
    "memory.remember":   ("remember_fact", {"key": ("str", True, 60), "value": ("str", True, 600)}),
    "home.state":        ("get_home_state", {}),
    "home.light.status": ("get_switchboard_status", {}),
    "home.light.control": ("control_switchboard_relay", {"relay": ("str", True, 40),
                                                         "action": ("enum", True, ("on", "off", "toggle")),
                                                         "brightness": ("int", False, (1, 100))}),
    "home.fan.status":   ("get_bedroom_fan_status", {}),
    # AV sensor box (temperature, humidity, light, PIR + the LD2410C radar: is anybody in the room, even sitting still)
    "home.room":         ("esp_status", {}),
    "home.plug.status":  ("get_plug_power", {}),
    "home.fan.control":  ("control_bedroom_fan", {"action": ("enum", True, ("on", "off", "toggle")),
                                                  "speed": ("int", False, (1, 5))}),
    "calendar.today":    ("get_calendar_today", {}),
    "email.important":   ("get_unread_important_emails", {}),
    "weather.now":       ("get_weather", {"place": ("str", False, 60)}),
    # Priya owns the Almanac (through Layla's bridge; vaults are never reachable)
    "almanac.summary":   ("almanac_today", {}),
    "almanac.changes":   ("almanac_changes", {"since": ("int", False, (0, 10 ** 12))}),
    "almanac.add":       ("almanac_add", {"kind": ("enum", True, ("reminder", "event", "shopping", "expense", "note", "alarm")),
                                          "title": ("str", True, 120), "date": ("str", False, 10), "time": ("str", False, 8),
                                          "repeat": ("enum", False, ("none", "daily")), "qty": ("str", False, 8),
                                          "amount": ("str", False, 12), "category": ("str", False, 24),
                                          "type": ("enum", False, ("spent", "received")), "text": ("str", False, 1000),
                                          "location": ("str", False, 80), "days": ("str", False, 40)}),
    "almanac.done":      ("almanac_mark_done", {"kind": ("enum", True, ("reminder", "shopping")),
                                                "title": ("str", True, 120)}),
    # Nitya (home) may leave a NOTE or a REMINDER in his Almanac -- never alarms, events, money or shopping.
    "almanac.home_note": ("almanac_add", {"kind": ("enum", True, ("note", "reminder")), "title": ("str", True, 120),
                                          "text": ("str", False, 600), "date": ("str", False, 10),
                                          "time": ("str", False, 8)}),
}
_COMMON = ["web.search", "memory.recall", "memory.remember"]
DEFAULT_ALLOW = {
    "naina": _COMMON, "megha": _COMMON, "veda": _COMMON, "shruti": _COMMON, "maya": _COMMON, "kavya": _COMMON,
    "priya": _COMMON + ["calendar.today", "email.important", "weather.now", "home.room",
                        "almanac.summary", "almanac.changes", "almanac.add", "almanac.done"],
    "lydia": _COMMON + ["email.important", "almanac.summary"],
    "nitya": ["memory.recall", "memory.remember", "home.state", "home.light.status", "home.light.control",
              "home.fan.status", "home.fan.control", "home.room", "home.plug.status",
              "almanac.summary", "almanac.home_note"],
}

TOOLS = [
    tool("assign_agent_task",
         "As the BOSS of the nine Layla-365 agents, give one a task. They pick it up on their next tick "
         "(within a minute) and report back. Agents: naina (engineer), megha (researcher), veda (inventor), "
         "priya (doctor & life, owns Almanac), nitya (home), shruti (music), lydia (finance), maya (B2B "
         "outreach), kavya (brand/media).",
         {"agent": S, "task": S, "priority": {"type": "string", "enum": ["low", "normal", "high"]}},
         ["agent", "task"]),
    tool("agent_status", "Check whether the nine agents are alive, paused or silent, and what each last did.", {}, []),
    tool("agent_reports", "Read what the agents reported recently (daily reports, alerts, notes).",
         {"agent": S, "days": I}, []),
    tool("pause_agent", "Pause or resume one agent (or 'all'). A paused agent's requests are refused.",
         {"agent": S, "paused": {"type": "boolean"}}, ["agent", "paused"]),
]
NAMES = {t["function"]["name"] for t in TOOLS}
KEYWORDS = ("agent", "agents", "naina", "megha", "veda", "priya", "nitya", "shruti", "lydia", "maya", "kavya",
            "team", "your workers", "assign", "briefing", "what did they do", "pause")


def team_line():
    """Appended to Layla's system prompt so she knows her team is NOT in his phone contacts."""
    roster = "; ".join(f"{a.capitalize()} ({r})" for a, r in ROLES.items())
    return (" You are also the BOSS of nine autonomous agents who work for Avishkar on a separate server: "
            + roster + ". They are your team, NOT people in his contacts or phone. When he asks you to give "
            "one of them work, call assign_agent_task; to see how they are doing call agent_status or "
            "agent_reports. After assigning, just confirm briefly that you've handed it over and that you'll "
            "report back -- never ask for a phone contact.")


def init(**deps):
    _D.update(deps)


def _mem():
    return _D["memory"]


# ---------------- config / state ----------------
def _conf():
    try:
        mt = os.path.getmtime(CONF)
    except OSError:
        return {}
    if mt != _cache["mt"]:
        with open(CONF, encoding="utf-8") as f:
            _cache["conf"] = json.load(f)
        _cache["mt"] = mt
    return _cache["conf"]


def _paused():
    try:
        mt = os.path.getmtime(STATE)
        if mt != _cache["smt"]:
            with open(STATE, encoding="utf-8") as f:
                _cache["state"] = json.load(f)
            _cache["smt"] = mt
    except OSError:
        return set()
    return set(_cache["state"].get("paused", []))


def _set_paused(names):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump({"paused": sorted(names)}, f)
    _cache["smt"] = None


def _client_ip(h):
    peer = h.client_address[0]
    if peer in ("127.0.0.1", "::1"):                 # only nginx on loopback may vouch for the real IP
        return (h.headers.get("X-Real-IP") or peer).strip()
    return peer


def _audit(rec):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ---------------- validation ----------------
def _validate(action, args):
    spec = ACTIONS[action][1]
    if not isinstance(args, dict):
        return None, "args must be an object"
    extra = set(args) - set(spec)
    if extra:
        return None, f"unknown args: {sorted(extra)}"
    out = {}
    for k, (typ, req, lim) in spec.items():
        if k not in args or args[k] in (None, ""):
            if req:
                return None, f"missing arg {k}"
            continue
        v = args[k]
        if typ == "str":
            if not isinstance(v, str) or len(v) > lim:
                return None, f"{k}: string up to {lim} chars"
        elif typ == "enum":
            if v not in lim:
                return None, f"{k}: one of {list(lim)}"
        elif typ == "int":
            try:
                v = int(v)
            except Exception:
                return None, f"{k}: integer"
            if not (lim[0] <= v <= lim[1]):
                return None, f"{k}: {lim[0]}..{lim[1]}"
        out[k] = v
    return out, ""


def _describe(action):
    """Human/LLM-readable arg spec for an action: {"arg": "string<=300 | one of [on, off] | int 1..5 (optional)"}."""
    out = {}
    for k, (typ, req, lim) in ACTIONS[action][1].items():
        t = f"string<={lim}" if typ == "str" else f"one of {list(lim)}" if typ == "enum" else f"int {lim[0]}..{lim[1]}"
        out[k] = t + ("" if req else " (optional)")
    return out


# ---------------- gateway ----------------
def _reports():
    return _mem().recall("long_term", REPORTS_KEY) or []


def handle(h, data):
    """POST /agent/gateway -- wired from do_POST; has its own auth (not owner cookie)."""
    t0 = time.time()
    ip = _client_ip(h)
    agent = (h.headers.get("X-L365-Agent") or "").strip().lower()
    body = data if isinstance(data, dict) else {}
    verb = str(body.get("verb", "")).strip()
    what = str(body.get("action", ""))[:60] if verb == "request" else ""

    def done(code, obj, why=""):
        _audit({"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "agent": agent, "ip": ip, "verb": verb, "action": what,
                "code": code, "why": why, "ms": int((time.time() - t0) * 1000)})
        return h._json(code, obj)

    if os.path.exists(KILL):
        return done(503, {"error": "gateway disabled"}, "kill-switch")
    c = _conf()
    if not c:
        return done(503, {"error": "gateway not configured"}, "no-config")
    if ip not in c.get("allowed_ips", []):
        return done(403, {"error": "forbidden"}, "ip")
    spec = (c.get("agents") or {}).get(agent)
    tok = h.headers.get("X-L365-Token", "")
    expected = (spec or {}).get("token_sha256", "")
    if agent not in AGENTS or not spec or not hmac.compare_digest(hashlib.sha256(tok.encode()).hexdigest(), expected):
        return done(401, {"error": "unauthorized"}, "token")
    now = time.time()
    with _lock:
        win = [x for x in _hits.get(agent, []) if now - x < 60]
        if len(win) >= int(spec.get("rate_per_min", 20)):
            _hits[agent] = win
            return done(429, {"error": "rate limited"}, "rate-min")
        win.append(now)
        _hits[agent] = win
        # heartbeat/inbox are bookkeeping polls (2 per 30s tick ~ 2,900/day); counting them exhausted the
        # daily budget by ~13:10 IST every day and silently blocked all afternoon duties.
        if verb not in ("heartbeat", "inbox"):
            d, n = _day.get(agent, (now_ist().date(), 0))
            if d != now_ist().date():
                d, n = now_ist().date(), 0
            if n >= int(spec.get("per_day", 3000)):
                return done(429, {"error": "daily limit"}, "rate-day")
            _day[agent] = (d, n + 1)

    # heartbeats and inbox polls are always allowed (even when paused) so Layla can see + resume them
    if verb == "heartbeat":
        info = body.get("info") if isinstance(body.get("info"), dict) else {}
        st = _mem().recall("long_term", STATUS_KEY) or {}
        st[agent] = {"at": now, "paused": agent in _paused() or "all" in _paused(),
                     "info": {k: str(v)[:80] for k, v in list(info.items())[:8]}}
        _mem().remember("long_term", STATUS_KEY, st)
        return done(200, {"ok": True, "paused": st[agent]["paused"]}, "ok")
    if verb == "inbox":
        if agent in _paused() or "all" in _paused():
            return done(200, {"ok": True, "tasks": [], "paused": True}, "paused")
        with _lock:
            allt = _mem().recall("long_term", TASKS_KEY) or []
            mine = [t for t in allt if t["agent"] == agent and t["status"] == "queued"][:5]
            for t in mine:
                t["status"] = "delivered"
                t["delivered_at"] = now
            _mem().remember("long_term", TASKS_KEY, allt[-300:])
        allow_now = spec.get("allow") or DEFAULT_ALLOW.get(agent, [])
        return done(200, {"ok": True, "actions": {a: _describe(a) for a in allow_now if a in ACTIONS},
                          "tasks": [{k: t[k] for k in ("id", "task", "priority", "created")} for t in mine]}, "ok")
    if verb == "task_done":
        tid = str(body.get("id", ""))
        with _lock:
            allt = _mem().recall("long_term", TASKS_KEY) or []
            for t in allt:
                if t["id"] == tid and t["agent"] == agent:
                    t["status"] = "done" if body.get("ok", True) else "failed"
                    t["result"] = str(body.get("result", ""))[:600]
                    t["done_at"] = now
            _mem().remember("long_term", TASKS_KEY, allt[-300:])
        return done(200, {"ok": True}, "ok")
    if verb == "report":
        kind = str(body.get("kind", "note"))
        if kind not in ("daily", "alert", "note"):
            return done(400, {"error": "kind must be daily|alert|note"}, "bad-kind")
        sev = str(body.get("severity", "info"))
        rec = {"id": uuid.uuid4().hex[:8], "agent": agent, "kind": kind, "severity": sev if sev in ("info", "warn", "critical") else "info",
               "title": str(body.get("title", ""))[:120], "body": str(body.get("body", ""))[:MAX_OUT], "at": now}
        with _lock:
            r = _reports()
            r.append(rec)
            _mem().remember("long_term", REPORTS_KEY, r[-400:])
        if kind == "alert" and rec["severity"] in ("warn", "critical"):
            with _lock:
                al = [x for x in _alerts.get(agent, []) if now - x < 3600]
                allow = len(al) < 3
                if allow:
                    al.append(now)
                _alerts[agent] = al
            if allow and flag("L365_ALERTS"):
                try:
                    _D["push"]({"type": "notify", "tone": "serious" if rec["severity"] == "critical" else "calm",
                                "text": f"{agent.capitalize()} flagged: {rec['title']}"})
                except Exception:
                    pass
        return done(200, {"ok": True, "id": rec["id"]}, "ok")
    if verb == "request":
        if agent in _paused() or "all" in _paused():
            return done(423, {"error": "agent is paused by Layla"}, "paused")
        action = str(body.get("action", ""))
        if action not in ACTIONS:
            return done(403, {"error": "unknown action"}, "no-such-action")
        allow = spec.get("allow") or DEFAULT_ALLOW.get(agent, [])
        if action not in allow:
            return done(403, {"error": "action not allowed for this agent"}, "allowlist")
        args, err = _validate(action, body.get("args") or {})
        if args is None:
            return done(400, {"error": err}, "bad-args")
        if action == "memory.remember":
            args["key"] = f"agent_{agent}_" + "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in args["key"].lower())[:50]
        try:
            res = _D["execute_tool"](ACTIONS[action][0], args)
            res = json.loads(json.dumps(res, default=str))
            out = str(res.get("output") if isinstance(res, dict) and "output" in res else res)[:MAX_OUT]
            status = res.get("status", "success") if isinstance(res, dict) else "success"
        except Exception as e:  # noqa: BLE001
            return done(500, {"error": f"{type(e).__name__}"}, "exception")
        return done(200, {"ok": status == "success", "output": out}, "ok")
    return done(400, {"error": "unknown verb"}, "bad-verb")


# ---------------- Layla's side: boss tools ----------------
def _ago(ts):
    s = max(0, time.time() - ts)
    return "just now" if s < 90 else f"{int(s // 60)} min ago" if s < 3600 else \
        f"{int(s // 3600)} h ago" if s < 86400 else f"{int(s // 86400)} d ago"


def agent_status():
    st = _mem().recall("long_term", STATUS_KEY) or {}
    paused = _paused()
    lines = []
    for a in AGENTS:
        s = st.get(a)
        if not s:
            lines.append(f"{a} ({ROLES[a]}): never checked in")
            continue
        alive = time.time() - s["at"] < 600
        flag_ = "PAUSED" if (a in paused or "all" in paused) else ("alive" if alive else "SILENT")
        lines.append(f"{a} ({ROLES[a]}): {flag_}, last seen {_ago(s['at'])}"
                     + (f" -- {', '.join(f'{k}={v}' for k, v in s['info'].items())}" if s.get("info") else ""))
    return "; ".join(lines)


def agent_reports(agent="", days=2):
    try:
        days = max(1, int(days or 2))
    except (TypeError, ValueError):          # the model sometimes passes "today"
        days = 1 if str(days).strip().lower() == "today" else 2
    cut = time.time() - days * 86400
    who = str(agent or "").strip().lower()
    if who in ("all", "everyone", "team", "agents", "all agents", "any", "none", "*"):
        who = ""
    rs = [r for r in _reports() if r["at"] >= cut and (not who or r["agent"] == who)]
    if not rs:
        return "No reports from the agents in that period."
    # "No tasks were assigned today" daily lines are noise next to real findings: keep them only for an
    # agent that has nothing else. Alerts first, then each agent's latest two real reports.
    boring = lambda r: r["kind"] == "daily" and re.match(r"\s*no tasks", r["body"] or "", re.I)
    by = {}
    for r in sorted(rs, key=lambda r: -r["at"]):
        by.setdefault(r["agent"], []).append(r)
    picked = []
    for a, lst in by.items():
        real = [r for r in lst if not boring(r)]
        picked += (real[:2] if real else lst[:1])
    picked.sort(key=lambda r: (r["kind"] != "alert", -r["at"]))
    clean = lambda t: re.sub(r"[*#`_]+", "", str(t or "")).replace("\n", " ")
    return "Agent reports (newest first, alerts on top):\n" + "\n".join(
        f"[{r['agent']} {r['kind']}/{r['severity']} {_ago(r['at'])}] {clean(r['title'])}: {clean(r['body'])[:320]}"
        for r in picked[:16])


def call(name, args):
    args = args or {}
    try:
        if name == "assign_agent_task":
            a = str(args.get("agent", "")).strip().lower()
            if a not in AGENTS:
                return {"status": "error", "error": f"unknown agent; choose from {', '.join(AGENTS)}"}
            task = str(args.get("task", "")).strip()[:800]
            if not task:
                return {"status": "error", "error": "need a task"}
            with _lock:
                allt = _mem().recall("long_term", TASKS_KEY) or []
                t = {"id": uuid.uuid4().hex[:8], "agent": a, "task": task, "priority": args.get("priority") or "normal",
                     "created": time.time(), "status": "queued"}
                allt.append(t)
                _mem().remember("long_term", TASKS_KEY, allt[-300:])
            return {"status": "success", "output": f"Assigned to {a} (task {t['id']}); they'll pick it up on their next tick and report back."}
        if name == "agent_status":
            return {"status": "success", "output": agent_status()}
        if name == "agent_reports":
            return {"status": "success", "output": agent_reports(args.get("agent", ""), args.get("days", 2))}
        if name == "pause_agent":
            a = str(args.get("agent", "")).strip().lower()
            if a != "all" and a not in AGENTS:
                return {"status": "error", "error": "unknown agent"}
            p = _paused()
            (p.add if args.get("paused") else p.discard)(a)
            _set_paused(p)
            return {"status": "success", "output": f"{a} {'paused' if args.get('paused') else 'resumed'}."}
        return {"status": "error", "error": f"unknown tool {name}"}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}


# ---------------- morning briefing ----------------
_BRIEF = """You are Layla, boss of nine agents, briefing your owner Avishkar for the morning. Below are your
agents' reports since last evening. Write a SHORT spoken briefing (max 90 words): what got done, anything
that needs his attention first, then one line on anything stuck or silent. Plain sentences, no lists, no
markdown. If there is nothing notable, say it was a quiet night in one sentence."""


def make_briefing(force=False):
    cut = time.time() - 16 * 3600
    rs = [r for r in _reports() if r["at"] >= cut]
    st = agent_status()
    material = "\n".join(f"{r['agent']} ({r['kind']}/{r['severity']}): {r['title']} -- {r['body'][:400]}" for r in rs[-20:]) \
        or "(no reports filed)"
    text = llm(_BRIEF, f"REPORTS:\n{material}\n\nAGENT STATUS: {st}", max_tokens=300)
    b = _mem().recall("long_term", BRIEF_KEY) or []
    b.append({"at": time.time(), "text": text})
    _mem().remember("long_term", BRIEF_KEY, b[-60:])
    _D["push"]({"type": "notify", "tone": "warm", "text": text})
    if _D.get("log_said"):
        _D["log_said"](text)
    return text


def _loop():
    time.sleep(180)
    while True:
        try:
            n = now_ist()
            b = _mem().recall("long_term", BRIEF_KEY) or []   # persisted, so a restart can't re-brief
            last = _dt.datetime.fromtimestamp(b[-1]["at"], IST).date() if b else None
            if flag("L365_BRIEFING") and BRIEF_HOUR_IST <= n.hour < 18 and last != n.date():
                print(f"[l365] briefing: {make_briefing()[:80]!r}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[l365] briefing failed: {type(e).__name__}: {e}", flush=True)
        time.sleep(900)


def start():
    threading.Thread(target=_loop, daemon=True, name="l365-boss").start()
