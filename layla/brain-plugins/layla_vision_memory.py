"""Layla visual memory -- Task 1, capability #2 (vision grounding + spatial).

Before this, every camera look produced one casual sentence and was then
forgotten. Now each explicit look (/see, /scan_room, /scan_room_tv) also gets
a background *grounding* pass: the vision model lists the objects in frame with
colour, left/center/right, near/middle/far and what they sit on or next to.

* recall_seen          -- "where did I leave my keys?" answered from that log.
* ask_about_last_view  -- follow-ups ("what colour was it?") answered from the
                          last frame, held in RAM only for 10 minutes; no new
                          capture.
* context_line()       -- short-term visual continuity in her context.

Privacy: frames are never written to disk; only the text notes are stored
(long_term "vision:log", capped). Kill switch: VISION_MEMORY=0 in .env.
Never raises into the caller.
"""
import datetime as _dt
import json
import os
import re
import threading
import time
import urllib.request
from zoneinfo import ZoneInfo

LOG_KEY = "vision:log"
LOG_CAP = 300
FRAME_TTL = 600          # seconds a frame stays usable for follow-ups
CONTEXT_TTL = 1800       # seconds a look stays in her always-on context
MIN_GAP = 4              # seconds between grounding calls
IST = ZoneInfo("Asia/Kolkata")

_D = {}                  # memory, groq_key, model, gemini_key, fallback_model, fallback_url, see
_lock = threading.Lock()
_last = {"at": 0.0, "image": None, "source": ""}
_last_ground = [0.0]

_GROUND = """List what is visible in this camera frame. Return ONLY JSON:
{"scene": "one plain sentence: what kind of place this is and what is happening",
 "people": <number of people visible>,
 "objects": [{"name": "short common noun, e.g. phone, water bottle, keys, laptop, mug",
              "color": "main colour, or empty",
              "where": "left | center | right  (as seen from the camera)",
              "depth": "near | middle | far",
              "relation": "short phrase about what it is on / next to / under, e.g. on the desk next to the laptop"}]}
Rules: at most 15 objects, only things clearly visible, skip walls/floor/ceiling/lighting,
never guess brand names or read text, never describe people's bodies -- just count them."""

TOOLS = [
    {"type": "function", "function": {"name": "recall_seen",
        "description": "Search your VISUAL memory -- notes of what you saw in earlier camera looks -- "
                        "to answer 'where did I leave my keys', 'have you seen my bottle', 'what was on "
                        "my desk earlier', 'when did you last see my phone'. This does NOT look through "
                        "the camera now; it only knows looks that already happened. If it finds "
                        "nothing, say so honestly and offer to look now with look_through_camera.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "the object or thing to find, e.g. 'keys', 'blue mug'"}},
            "required": ["query"]}}},
    {"type": "function", "function": {"name": "ask_about_last_view",
        "description": "Answer a FOLLOW-UP question about the camera frame you looked at in the last "
                        "10 minutes ('what colour was it', 'what was on the left', 'how many cups were "
                        "there') without taking a new picture. If it reports there is no recent frame, "
                        "call look_through_camera instead.",
        "parameters": {"type": "object", "properties": {
            "question": {"type": "string"}}, "required": ["question"]}}},
]
NAMES = {t["function"]["name"] for t in TOOLS}
KEYWORDS = (
    "where did i", "where is my", "where are my", "where's my", "wheres my", "left my", "kept my",
    "have you seen", "did you see", "you saw", "last saw", "last see", "you just saw",
    "what colour", "what color", "how many", "on the left", "on the right", "next to",
    "in that picture", "in the picture", "in that photo", "in that frame", "on my desk", "on the table",
)


def enabled():
    return os.environ.get("VISION_MEMORY", "1") != "0"


def init(**deps):
    _D.update(deps)


# ---------------- grounding ----------------
def _parse_json(raw):
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip())
    m = re.search(r"\{.*\}", raw, re.S)
    return json.loads(m.group(0) if m else raw)


def _vision_json(image_b64):
    msgs = [{"role": "user", "content": [
        {"type": "text", "text": _GROUND},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}]}]
    attempts = [
        ("https://api.groq.com/openai/v1/chat/completions", _D.get("groq_key"),
         {"model": _D.get("model"), "reasoning_effort": "none"}),
        (_D.get("fallback_url"), _D.get("gemini_key"), {"model": _D.get("fallback_model")}),
    ]
    last_err = None
    for url, key, extra in attempts:
        if not url or not key:
            continue
        try:
            body = dict(extra, messages=msgs, max_tokens=700, temperature=0.1)
            req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={
                "Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "layla/1.0"})
            with urllib.request.urlopen(req, timeout=40) as r:
                d = json.loads(r.read())
            return _parse_json(d["choices"][0]["message"].get("content") or "")
        except Exception as e:
            last_err = e
    raise RuntimeError(f"grounding failed: {last_err}")


def _clean(obs):
    objs = []
    for o in (obs.get("objects") or [])[:15]:
        if not isinstance(o, dict) or not str(o.get("name", "")).strip():
            continue
        objs.append({k: str(o.get(k, "")).strip()[:80] for k in ("name", "color", "where", "depth", "relation")})
    try:
        people = int(obs.get("people") or 0)
    except Exception:
        people = 0
    return {"scene": str(obs.get("scene", "")).strip()[:300], "people": people, "objects": objs}


def ground(image_b64, source):
    """Synchronous: frame -> stored observation. Returns the entry (or None)."""
    obs = _clean(_vision_json(image_b64))
    entry = dict(obs, at=time.time(), source=source)
    with _lock:
        log = _D["memory"].recall("long_term", LOG_KEY) or []
        log.append(entry)
        _D["memory"].remember("long_term", LOG_KEY, log[-LOG_CAP:])
    return entry


def observe(image_b64, source="room webcam"):
    """Hook for every explicit look. Keeps the frame in RAM at once (so a
    follow-up works immediately) and grounds it in the background."""
    if not enabled() or not image_b64:
        return
    _last.update(at=time.time(), image=image_b64, source=source)
    if time.time() - _last_ground[0] < MIN_GAP:
        return
    _last_ground[0] = time.time()

    def _run():
        try:
            e = ground(image_b64, source)
            print(f"[vision-mem] {source}: {len(e['objects'])} objects, {e['people']} people", flush=True)
        except Exception as ex:
            print(f"[vision-mem] skipped: {ex}", flush=True)
    threading.Thread(target=_run, daemon=True, name="vision-mem").start()


# ---------------- recall ----------------
_STOP = {"my", "the", "a", "an", "where", "did", "do", "does", "i", "is", "are", "was", "were", "you",
         "see", "saw", "seen", "last", "have", "has", "leave", "left", "keep", "kept", "put", "it", "of",
         "when", "what", "any", "anything", "earlier", "today", "on", "in", "at", "to", "me", "can",
         "find", "lost", "misplaced", "your", "time", "thing", "things"}


def _stem(w):
    w = w.lower()
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("es") and w[-3] in "sxz":
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def _terms(text):
    return {_stem(w) for w in re.findall(r"[a-zA-Z]+", text or "") if w.lower() not in _STOP}


def _ago(ts):
    s = max(0, time.time() - ts)
    if s < 90:
        rel = "just now"
    elif s < 3600:
        rel = f"about {int(s // 60)} minutes ago"
    elif s < 86400:
        h = int(s // 3600)
        rel = f"about {h} hour{'s' if h > 1 else ''} ago"
    else:
        d = int(s // 86400)
        rel = f"{d} day{'s' if d > 1 else ''} ago"
    when = _dt.datetime.fromtimestamp(ts, IST).strftime("%a %d %b, %I:%M %p").replace(" 0", " ")
    return f"{rel} ({when})"


def _place(o):
    bits = []
    if o.get("relation"):
        bits.append(o["relation"])
    side = {"left": "on the left side", "right": "on the right side", "center": "in the middle"}.get(
        (o.get("where") or "").lower())
    if side:
        bits.append(side + " of the frame")
    if (o.get("depth") or "").lower() in ("near", "far"):
        bits.append("close to the camera" if o["depth"].lower() == "near" else "far from the camera")
    return ", ".join(bits)


def recall_seen(query, max_hits=3):
    log = _D["memory"].recall("long_term", LOG_KEY) or []
    if not log:
        return "I have no visual memory yet -- I only remember things from camera looks you ask me for."
    want = _terms(query)
    if not want:
        last = log[-1]
        return f"The last thing I saw was {_ago(last['at'])} through the {last['source']}: {last['scene']}"
    hits = []
    for e in reversed(log):
        for o in e.get("objects", []):
            if _terms(o.get("name", "")) & want:
                if not hits or _place(hits[-1][1]) != _place(o):   # same spot again is not news
                    hits.append((e, o))
                break
        if len(hits) >= max_hits:
            break
    if not hits:
        oldest = log[0]["at"]
        return (f"I don't remember seeing any {' '.join(sorted(want))} in my camera looks since {_ago(oldest)}. "
                "I only remember what was in frame when you asked me to look.")
    e, o = hits[0]
    desc = " ".join(x for x in (o.get("color"), o.get("name")) if x)
    out = f"Last seen: {desc}, {_place(o) or 'in frame'} -- {_ago(e['at'])}, through the {e['source']}."
    if len(hits) > 1:
        out += " Earlier sightings: " + "; ".join(
            f"{_ago(h[0]['at'])}: {_place(h[1]) or 'in frame'}" for h in hits[1:])
    out += " (This is memory, not a live view -- it may have moved since.)"
    return out


def ask_about_last_view(question):
    age = time.time() - _last["at"]
    if not _last["image"] or age > FRAME_TTL:
        return None
    return _D["see"](_last["image"], question)


def context_line():
    try:
        if not enabled():
            return ""
        log = _D["memory"].recall("long_term", LOG_KEY) or []
        if not log or time.time() - log[-1]["at"] > CONTEXT_TTL:
            return ""
        e = log[-1]
        objs = ", ".join(" ".join(x for x in (o.get("color"), o.get("name")) if x) for o in e["objects"][:10])
        return (f"Your last camera look ({_ago(e['at'])}, {e['source']}): {e['scene']}"
                + (f" Visible: {objs}." if objs else ""))[:500]
    except Exception:
        return ""


# ---------------- tool dispatch ----------------
def call(name, args):
    args = args or {}
    try:
        if not enabled():
            return {"status": "error", "error": "visual memory is switched off"}
        if name == "recall_seen":
            return {"status": "success", "output": recall_seen(args.get("query", ""))}
        if name == "ask_about_last_view":
            ans = ask_about_last_view(args.get("question", "") or "What do you see?")
            if ans is None:
                return {"status": "success", "output": "(no camera frame from the last 10 minutes -- "
                        "call look_through_camera to take a fresh look instead)"}
            return {"status": "success", "output": ans}
        return {"status": "error", "error": f"unknown tool {name}"}
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
