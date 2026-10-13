"""Layla ambient autonomy -- Task 1, capability #5 (continuous ambient autonomy).

Before: she only spoke first through fixed loops (reminders, greeting).
Now she keeps her OWN goals -- seeded from what he left unfinished (episode
open loops, #1) -- and every 15 minutes a small loop looks at her signals:

  her goals - his recent mood (#3) - body signals (#9) - the time of day -
  how long he's been quiet

...and decides whether there is ONE thing genuinely worth saying now (a check-
in, a follow-up on something he left open, a gentle nudge). Most ticks she
decides to stay quiet.

Hard limits (code, not prompt): only during waking hours, only while a Layla
screen is open, never mid-conversation, at most 4 times a day and 90 minutes
apart. She only TALKS -- this loop has no access to tools, devices or other
people. Kill switch: AMBIENT=0.
"""
import datetime as _dt
import threading
import time
import uuid

from layla_plugin_util import S, flag, fmt_ts, llm_json, now_ist, tool

GOALS_KEY = "ambient:goals"
LOG_KEY = "ambient:log"
TICK_S = 15 * 60
START_H, END_H = 9, 22
MAX_PER_DAY = 4
MIN_GAP_S = 90 * 60
QUIET_AFTER_TURN_S = 3 * 60
ACTIVE_WINDOW_S = 4 * 3600

_D = {}       # memory, push, screens_open, epi, affect, telemetry, log_said
_state = {"last_user": 0.0}

TOOLS = [
    tool("list_my_goals",
         "List YOUR OWN ongoing goals for helping him (things he left unfinished that you are quietly "
         "following up on), with their status.", {}, []),
    tool("update_my_goal",
         "Mark one of your own goals done or dropped (e.g. when he says he finished it or doesn't want "
         "reminding), or add a new one he asks you to keep an eye on.",
         {"id": S, "status": {"type": "string", "enum": ["active", "done", "dropped"]}, "add_text": S}, []),
]
NAMES = {"list_my_goals", "update_my_goal"}
KEYWORDS = ("your goals", "my goals", "follow up", "keep an eye", "keep track", "stop reminding",
            "remind me about", "don't remind", "dont remind")

_DECIDE = """You are Layla deciding, on your own initiative, whether to say ONE short thing to Avishkar right now.
Most of the time the right answer is to stay quiet. Speak only if something is genuinely useful or caring now:
following up on one of your goals, checking in if he's seemed low, a gentle nudge from his body signals.
Never repeat something said in RECENTLY SAID. Never diagnose. Never be clingy.
Return ONLY JSON: {"speak": true/false, "text": "max 2 short spoken sentences", "tone": "warm|calm|playful|sympathetic",
"goal_id": "id of the goal this advances or empty", "why": "short reason"}"""


def init(**deps):
    _D.update(deps)


def note_activity():
    _state["last_user"] = time.time()


def _goals():
    return _D["memory"].recall("long_term", GOALS_KEY) or []


def _save_goals(g):
    _D["memory"].remember("long_term", GOALS_KEY, g[-60:])


def seed_goals_from_episodes(days=3):
    epi = _D.get("epi")
    if epi is None:
        return 0
    goals = _goals()
    known = {g["text"].lower() for g in goals}
    added = 0
    for d in sorted(epi._index())[-days:]:
        for loop in (epi.get_day(d) or {}).get("open_loops", []):
            t = str(loop).strip()
            if t and t.lower() not in known:
                goals.append({"id": uuid.uuid4().hex[:6], "text": t, "source": f"open loop {d}",
                              "created": time.time(), "status": "active", "nudges": 0, "last_nudge": 0})
                known.add(t.lower())
                added += 1
    # goals older than 10 days with no progress quietly expire
    for g in goals:
        if g["status"] == "active" and time.time() - g["created"] > 10 * 86400:
            g["status"] = "expired"
    _save_goals(goals)
    return added


def _log():
    return _D["memory"].recall("long_term", LOG_KEY) or []


def _gates():
    now = now_ist()
    if not flag("AMBIENT"):
        return "off"
    if not (START_H <= now.hour < END_H):
        return "quiet hours"
    if not _D["screens_open"]():
        return "no screen open"
    if time.time() - _state["last_user"] < QUIET_AFTER_TURN_S:
        return "mid-conversation"
    if time.time() - _state["last_user"] > ACTIVE_WINDOW_S:
        return "he hasn't been around"
    spoken = [e for e in _log() if e.get("spoke")]
    today = [e for e in spoken if _dt.datetime.fromtimestamp(e["at"], now.tzinfo).date() == now.date()]
    if len(today) >= MAX_PER_DAY:
        return "daily cap"
    if spoken and time.time() - spoken[-1]["at"] < MIN_GAP_S:
        return "too soon"
    return ""


def _signals():
    sig = []
    active = [g for g in _goals() if g["status"] == "active" and g.get("nudges", 0) < 2
              and time.time() - g.get("last_nudge", 0) > 86400]
    if active:
        sig.append("YOUR GOALS: " + "; ".join(f"[{g['id']}] {g['text']}" for g in active[:6]))
    aff = _D.get("affect")
    if aff is not None:
        try:
            if aff.needs_checkin():
                sig.append("MOOD: he has seemed low or stressed several times in the last couple of hours.")
        except Exception:
            pass
    tel = _D.get("telemetry")
    if tel is not None:
        try:
            sig += ["BODY: " + s for s in tel.signals()]
        except Exception:
            pass
    return sig


def tick(force=False):
    why_not = "" if force else _gates()
    if why_not:
        return f"skip: {why_not}"
    sig = _signals()
    if not sig:
        return "skip: nothing to consider"
    recent = [e["text"] for e in _log()[-6:] if e.get("spoke")]
    now = now_ist()
    user = (f"NOW: {now.strftime('%A %H:%M')} IST. He last spoke to you {int((time.time()-_state['last_user'])/60)} min ago.\n"
            + "\n".join(sig) + "\nRECENTLY SAID: " + (" | ".join(recent) or "(nothing)"))
    d = llm_json(_DECIDE, user, max_tokens=300)
    entry = {"at": time.time(), "spoke": bool(d.get("speak") and d.get("text")), "text": str(d.get("text", ""))[:300],
             "why": str(d.get("why", ""))[:200]}
    log = _log()
    log.append(entry)
    _D["memory"].remember("long_term", LOG_KEY, log[-300:])
    if not entry["spoke"]:
        return f"quiet: {entry['why']}"
    gid = str(d.get("goal_id") or "")
    if gid:
        goals = _goals()
        for g in goals:
            if g["id"] == gid:
                g["nudges"] = g.get("nudges", 0) + 1
                g["last_nudge"] = time.time()
        _save_goals(goals)
    _D["push"]({"type": "notify", "text": entry["text"], "tone": d.get("tone") or "warm"})
    if _D.get("log_said"):
        _D["log_said"](entry["text"])
    return f"spoke: {entry['text']}"


def _loop():
    time.sleep(240)
    last_seed = None
    while True:
        try:
            if last_seed != now_ist().date() and now_ist().hour >= 5:
                print(f"[ambient] goals seeded: {seed_goals_from_episodes()}", flush=True)
                last_seed = now_ist().date()
            r = tick()
            if not r.startswith("skip"):
                print(f"[ambient] {r}", flush=True)
        except Exception as e:
            print(f"[ambient] tick failed: {type(e).__name__}: {e}", flush=True)
        time.sleep(TICK_S)


def start():
    threading.Thread(target=_loop, daemon=True, name="ambient").start()


def call(name, args):
    args = args or {}
    try:
        if name == "list_my_goals":
            g = [x for x in _goals() if x["status"] in ("active", "done")][-12:]
            if not g:
                return {"status": "success", "output": "I'm not tracking any goals of my own right now."}
            return {"status": "success", "output": "; ".join(
                f"[{x['id']}] {x['text']} ({x['status']}, from {x['source']})" for x in g)}
        if name == "update_my_goal":
            goals = _goals()
            if args.get("add_text"):
                goals.append({"id": uuid.uuid4().hex[:6], "text": args["add_text"].strip(), "source": "he asked",
                              "created": time.time(), "status": "active", "nudges": 0, "last_nudge": 0})
                _save_goals(goals)
                return {"status": "success", "output": "Added -- I'll keep an eye on it."}
            for g in goals:
                if g["id"] == args.get("id"):
                    g["status"] = args.get("status") or "done"
                    _save_goals(goals)
                    return {"status": "success", "output": f"Marked {g['status']}."}
            return {"status": "success", "output": "I couldn't find that goal."}
        return {"status": "error", "error": f"unknown tool {name}"}
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
