"""Layla computer-use -- Task 1, capability #10 (active OS action / computer use).

The PC agent's own design note said screen control must wait for a real
approval UI. This is that UI plus the loop:

  operate_computer(goal) -> Allow/Deny card (or spoken yes) -> session opens
  on the PC (a visible red "Layla is controlling this PC -- STOP" banner) ->
  loop: screenshot -> vision model picks ONE action -> risky actions
  (send / submit / pay / delete / install / post / anything with passwords)
  pause for another approval -> PC agent executes -> repeat (max 20 steps).

Stop any time: the banner's STOP button, slamming the mouse into a screen
corner (pyautogui fail-safe), saying "stop", or COMPUTER_USE=0.
She never types passwords, OTPs or card numbers -- she hands those to him.

Talks to the PC agent over the internal MQTT listener with its own client id
(the shared-client-id trap is avoided). Never raises into the caller.
"""
import base64
import json
import threading
import time
import urllib.request
import uuid

from layla_plugin_util import S, UA, flag, parse_json, tool

DEVICE = "pc-001"
CMD = f"tryvanta/pc/{DEVICE}/cmd/cu"
RES = f"tryvanta/pc/{DEVICE}/cu/"
MAX_STEPS = 20
STEP_TIMEOUT = 25

_D = {}   # groq_key, model, gemini_key, fallback_model, fallback_url, approvals, push, log_said
_client = None
_waiters = {}
_wlock = threading.Lock()
_session = {"id": None, "goal": "", "status": "idle", "steps": [], "stop": False, "started": 0}

TOOLS = [
    tool("operate_computer",
         "Use his Windows PC like a person would -- look at the screen, click, type, scroll -- to get a task "
         "done ('open my downloads and find the invoice PDF', 'in Chrome, search flights to Delhi on Friday'). "
         "He must approve first (card or spoken yes) and approves again before anything that sends, submits, "
         "buys, deletes or posts. Prefer pc_open_app / pc_open_url for simple opens.",
         {"goal": S}, ["goal"]),
    tool("computer_task_status", "Report how the current or last computer task is going.", {}, []),
    tool("stop_computer_task", "Stop the computer task immediately.", {}, []),
]
NAMES = {t["function"]["name"] for t in TOOLS}
KEYWORDS = ("on my pc", "on my computer", "on my laptop", "on the computer", "click", "operate", "use my pc",
            "use my computer", "stop the computer", "computer task", "on screen", "my screen", "desktop")

_PLAN = """You operate a Windows PC for Avishkar, one action at a time, by looking at screenshots.
GOAL: {goal}
Coordinates: give x,y in a 0-1000 normalised space over the screenshot (0,0 top-left, 1000,1000 bottom-right),
pointing at the CENTRE of the element.
Return ONLY JSON:
{{"thought": "one short sentence about what you see and why",
  "action": "click|double_click|right_click|type|key|scroll|wait|done|fail|ask_owner",
  "x": 0-1000, "y": 0-1000, "text": "text to type", "keys": "e.g. ctrl+l, enter, alt+tab", "dy": -5..5,
  "risky": true/false, "say": "what to tell him if done/fail/ask_owner"}}
Rules: one action per turn. "risky": true for anything that sends, submits, pays, buys, deletes, installs,
posts, accepts terms or changes settings. NEVER type passwords, OTPs, PINs or card numbers -- use ask_owner.
If the goal is achieved say done. If stuck after a few tries say fail. Previous actions: {history}"""


def init(**deps):
    _D.update(deps)
    global _client
    try:
        import paho.mqtt.client as mqtt
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="layla-computeruse")
        c.on_connect = lambda cl, u, f, rc, p=None: cl.subscribe(RES + "#", 1)
        c.on_message = _on_msg
        c.connect("127.0.0.1", 51883, 30)
        c.loop_start()
        _client = c
    except Exception as e:
        print(f"[computer-use] mqtt unavailable: {e}", flush=True)


def _on_msg(c, u, msg):
    rid = msg.topic.rsplit("/", 1)[-1]
    with _wlock:
        w = _waiters.get(rid)
    if w is not None:
        try:
            w["res"] = json.loads(msg.payload.decode(errors="replace"))
        except Exception:
            w["res"] = {"ok": False, "error": "bad reply"}
        w["ev"].set()


def _rpc(op, timeout=STEP_TIMEOUT, **args):
    if _client is None:
        return {"ok": False, "error": "no mqtt"}
    rid = uuid.uuid4().hex[:12]
    w = {"ev": threading.Event(), "res": None}
    with _wlock:
        _waiters[rid] = w
    try:
        _client.publish(CMD, json.dumps({"req": rid, "op": op, "session": _session["id"], "args": args}), qos=1)
        if not w["ev"].wait(timeout):
            return {"ok": False, "error": "PC agent did not answer (offline or an older agent version)"}
        return w["res"] or {"ok": False, "error": "empty reply"}
    finally:
        with _wlock:
            _waiters.pop(rid, None)


def _vision(image_b64, prompt):
    msgs = [{"role": "user", "content": [{"type": "text", "text": prompt},
                                         {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}]}]
    last = None
    for url, key, extra in (("https://api.groq.com/openai/v1/chat/completions", _D.get("groq_key"),
                             {"model": _D.get("model"), "reasoning_effort": "none"}),
                            (_D.get("fallback_url"), _D.get("gemini_key"), {"model": _D.get("fallback_model")})):
        if not url or not key:
            continue
        try:
            body = dict(extra, messages=msgs, max_tokens=400, temperature=0.1)
            req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={
                "Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": UA})
            with urllib.request.urlopen(req, timeout=45) as r:
                return parse_json(json.loads(r.read())["choices"][0]["message"].get("content") or "")
        except Exception as e:
            last = e
    raise RuntimeError(f"vision failed: {last}")


def _tell(text):
    try:
        _D["push"]({"type": "notify", "text": text, "tone": "calm"})
        if _D.get("log_said"):
            _D["log_said"](text)
    except Exception:
        pass


def _await_approval(title, detail):
    ev, box = threading.Event(), {}

    def cb(allowed, via):
        box["ok"] = allowed
        ev.set()
        return "continuing" if allowed else "stopped"
    _D["approvals"].request("computer", title, detail, cb, ttl=300)
    ev.wait(310)
    return bool(box.get("ok"))


def _run(goal):
    sid = _session["id"]
    r = _rpc("session_start", goal=goal)
    if not r.get("ok"):
        _session["status"] = "failed"
        _tell(f"I couldn't take control of the PC: {r.get('error')}")
        return
    try:
        history = []
        for step in range(MAX_STEPS):
            if _session["stop"] or _session["id"] != sid or not flag("COMPUTER_USE"):
                _session["status"] = "stopped"
                _tell("Stopped controlling the PC.")
                return
            shot = _rpc("screenshot", timeout=30)
            if not shot.get("ok"):
                _session["status"] = "failed"
                _tell(f"Stopped: {shot.get('error')}")
                return
            plan = _vision(shot["image"], _PLAN.format(goal=goal, history=json.dumps(history[-8:])))
            act = str(plan.get("action", "")).lower()
            entry = {"step": step + 1, "action": act, "thought": str(plan.get("thought", ""))[:160]}
            _session["steps"].append(entry)
            if act == "done":
                _session["status"] = "done"
                _tell(plan.get("say") or "Done on the PC.")
                return
            if act in ("fail", "ask_owner"):
                _session["status"] = "needs_you" if act == "ask_owner" else "failed"
                _tell(plan.get("say") or ("I need you for this step." if act == "ask_owner" else "I couldn't finish that on the PC."))
                return
            if plan.get("risky"):
                what = plan.get("thought") or act
                if not _await_approval("Allow this step on your PC?", f"{goal}\n\nNext: {what}"):
                    _session["status"] = "stopped"
                    _tell("Okay, I stopped before that step.")
                    return
            w, h = shot.get("w", 1920), shot.get("h", 1080)
            args = {}
            if act in ("click", "double_click", "right_click"):
                args = {"x": int(float(plan.get("x", 500)) / 1000 * w), "y": int(float(plan.get("y", 500)) / 1000 * h)}
            elif act == "type":
                args = {"text": str(plan.get("text", ""))[:500]}
            elif act == "key":
                args = {"keys": str(plan.get("keys", ""))[:40]}
            elif act == "scroll":
                args = {"dy": max(-10, min(10, int(plan.get("dy", -3) or -3)))}
            elif act == "wait":
                time.sleep(2)
                history.append({"action": "wait"})
                continue
            else:
                history.append({"action": act, "note": "unknown action ignored"})
                continue
            res = _rpc(act, **args)
            history.append({"action": act, **args, "ok": res.get("ok"), "err": res.get("error")})
            if res.get("aborted"):
                _session["status"] = "stopped"
                _tell("You stopped me on the PC -- I've let go.")
                return
            time.sleep(0.8)
        _session["status"] = "failed"
        _tell("That took too many steps, so I stopped. Want me to try a different way?")
    except Exception as e:
        _session["status"] = "failed"
        _tell(f"Something went wrong on the PC side ({type(e).__name__}), so I stopped.")
    finally:
        _rpc("session_end", timeout=8)


def start_task(goal):
    if not flag("COMPUTER_USE"):
        return "Computer control is switched off."
    if _session["status"] in ("awaiting_approval", "running"):
        return f"I'm already on a PC task: {_session['goal']}"
    sid = uuid.uuid4().hex[:8]
    _session.update(id=sid, goal=goal, status="awaiting_approval", steps=[], stop=False, started=time.time())

    def cb(allowed, via):
        if _session["id"] != sid:
            return "stale"
        if not allowed:
            _session["status"] = "denied"
            return "Okay, I won't touch the PC."
        _session["status"] = "running"
        threading.Thread(target=_run, args=(goal,), daemon=True, name="computer-use").start()
        return "Starting on the PC now -- there's a STOP button on the PC screen."
    _D["approvals"].request("computer", "Let Layla control your PC?", goal, cb, ttl=300)
    return ("Waiting for his OK before touching the PC -- tell him in one line what you'll do and that he can "
            "tap Allow or just say yes. Do not claim you've started.")


def call(name, args):
    args = args or {}
    try:
        if name == "operate_computer":
            return {"status": "success", "output": start_task((args.get("goal") or "").strip()[:300])}
        if name == "computer_task_status":
            s = _session
            if not s["id"]:
                return {"status": "success", "output": "No computer task yet."}
            last = s["steps"][-1]["thought"] if s["steps"] else ""
            return {"status": "success", "output": f"Task '{s['goal']}': {s['status']}, {len(s['steps'])} steps. {last}"}
        if name == "stop_computer_task":
            _session["stop"] = True
            _rpc("session_end", timeout=5)
            return {"status": "success", "output": "Stopped."}
        return {"status": "error", "error": f"unknown tool {name}"}
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
