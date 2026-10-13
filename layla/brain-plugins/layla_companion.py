"""Conversation mode (owner idea 2026-10-12): live, back-and-forth companion talk.

"Layla, conversation mode on"  -> she switches from answer-and-stop to a friend on a call:
  short spoken turns, reacts to his reactions ("ha ha", "ohh", "avna"), keeps the thread going with a
  follow-up / an offer / a suggestion, drives brainstorming ("we can build it -- I'd do X, what do you think?").
"conversation mode off" / "end conversation" / "Layla end" -> back to normal.

Server-side state (single owner), auto-expires after 30 min of silence. The command turn itself is answered
instantly (no LLM). Kill switch: COMPANION=0. Never raises into the caller.
"""
import re
import time

from layla_plugin_util import flag

STATE_KEY = "companion:mode"
IDLE_EXPIRE_S = 30 * 60

_D = {}   # memory

ON_RE = re.compile(r"\b(?:conversation mode(?: is)? (?:on|start|started|activate|activated)|(?:start|turn on|switch on|enable|activate) "
                   r"(?:the )?conversation mode|companion mode on|let'?s (?:just )?(?:talk|chat) (?:like friends|for a while|for some time))\b", re.I)
OFF_RE = re.compile(r"\b(?:conversation mode(?: is)? (?:off|stop|end|over)|(?:stop|end|exit|turn off|switch off|disable) "
                    r"(?:the )?conversation(?: mode)?|companion mode off|(?:layla|laila|leela|lila)[,.!]?\s+(?:end|stop))\b", re.I)

TOOLS = []          # no tools: this plugin only shapes how she talks
NAMES = set()

_HINT = (
    "CONVERSATION MODE IS ON: you are in a live, back-and-forth voice chat with him, like a close friend on a call. "
    "Reply in one or two short spoken sentences (about 35 words at most). React to what he just said first. "
    "If he only reacted -- laughing, 'ohh', 'avna', 'hmm', 'ok', 'nice' -- respond to that reaction and keep the "
    "thread going (after a joke: 'Liked it? Want another one?'). Usually end with a natural follow-up question, an "
    "offer or a suggestion that moves the talk forward. When he shares an idea or plan, be genuinely excited, "
    "propose ONE concrete angle or option, then ask what he thinks; when it feels ready, nudge: 'so, shall we "
    "start?'. Never repeat a point you already made: if he only says 'ohh', 'hmm', 'avna?' or 'ok' after your "
    "suggestion, add something NEW -- another option ('there's also another way...'), one concrete detail, or a "
    "question that moves it forward. Never lecture, no lists, no markdown. Match his language: English, Telugu or Tenglish."
)


def init(**deps):
    _D.update(deps)


def _state():
    try:
        return _D["memory"].recall("short_term", STATE_KEY) or {}
    except Exception:
        return {}


def _save(st):
    try:
        _D["memory"].remember("short_term", STATE_KEY, st)
    except Exception:
        pass


def is_on():
    st = _state()
    if not st.get("on"):
        return False
    if time.time() - st.get("last", 0) > IDLE_EXPIRE_S:
        _save({"on": False, "since": 0, "last": 0, "reason": "idle-expired"})
        return False
    return True


def command(message):
    """Returns (reply, mode_change) for an on/off command, else None. Checked before the brain runs."""
    if not flag("COMPANION") or not message:
        return None
    m = message.strip()
    if OFF_RE.search(m):
        was = is_on()
        _save({"on": False, "since": 0, "last": time.time()})
        return ("Okay, conversation mode off. I'm here whenever you need me." if was
                else "Conversation mode wasn't on, but I'm right here."), "off"
    if ON_RE.search(m):
        _save({"on": True, "since": time.time(), "last": time.time()})
        return "Conversation mode on! I'm all yours. So, what's on your mind?", "on"
    return None


def turn_hint(message):
    if not flag("COMPANION") or not is_on():
        return ""
    st = _state()
    st["last"] = time.time()
    _save(st)
    return _HINT


def call(name, args):
    return {"status": "error", "error": "no tools"}
