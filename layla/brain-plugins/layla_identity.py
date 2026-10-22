"""Layla identity -- Task 4a (IdentityPresenceEngine): fuse face + voice into one "who am I talking to".

Before: face and voice each wrote into ONE shared slot (presence:last_face_identity), so a voice match
silently overwrote a face match, and a face the camera saw but could not name left no trace at all
(an old "Avishkar" stayed current for 30 minutes while a stranger sat down).

Now every identity signal is kept separately and fused per turn:

  owner_confirmed   voice + face agree it's the owner           -> silent (no behaviour change)
  owner_likely      owner by one signal, nothing contradicts it -> silent
  conflict          owner in view but the voice isn't his       -> caution, ask who's speaking
  owner_plus_others owner in view AND an unrecognised face      -> don't discuss private things aloud
  other_known       a named non-owner (family / friend / guest) -> role-based caution
  unknown           nobody recognised                           -> treat as a stranger

Multi-family: each enrolled person can get a role (family / friend / guest) via set_person_role; the
role only changes how careful she is, never what is stored. A match stays a SOFT signal, never auth.
Kill switch: IDENTITY_FUSION=0. Never raises into the caller.
"""
import time

from layla_plugin_util import S, flag, tool

ROLES_KEY = "identity:roles"
FACE_TTL = 300        # a face sighting stays current for 5 min (camera is polled, not continuous)
VOICE_TTL = 120
ROLE_WORDS = ("family", "friend", "guest")

_D = {}               # memory, speakers (module), owner
_sig = {}             # "face" -> {at, names, unknown}

TOOLS = [
    tool("who_is_here",
         "Say who Layla thinks she is talking to / who is in the room right now, combining the camera (faces) "
         "and the microphone (voice). States how sure she is and which signal each part comes from.",
         {}, []),
    tool("set_person_role",
         "Record how Layla should treat an enrolled person: family, friend or guest. Only changes how careful "
         "she is about Avishkar's private information around them.",
         {"name": S, "role": S}, ["name", "role"]),
]
NAMES = {"who_is_here", "set_person_role"}
KEYWORDS = ("who is here", "who's here", "who is in the room", "who's in the room", "who am i talking",
            "who are you talking", "is anyone else", "anyone with me", "set role", "is family", "is a friend",
            "is a guest", "treat him as", "treat her as")


def init(**deps):
    _D.update(deps)


def note(src, names=(), unknown=0):
    """Called by the face paths in layla_service.py. src='face'. Never raises."""
    try:
        _sig[src] = {"at": time.time(), "names": [n for n in (names or []) if n], "unknown": int(unknown or 0)}
    except Exception:
        pass


def _owner():
    return _D.get("owner") or "Avishkar"


def _roles():
    try:
        return _D["memory"].recall("long_term", ROLES_KEY) or {}
    except Exception:
        return {}


def _role(name):
    return _roles().get(name, "known")


def _voice(message=None):
    """-> None (no usable voice signal) | {'kind': 'name'|'unknown'|'multi', 'name', 'score'}"""
    sp = _D.get("speakers")
    if sp is None:
        return None
    try:
        known = sp._D["identities"]() or {}
        if not known:
            return None                          # nobody's voice enrolled: voice can't discriminate
        if message is not None:
            m = sp._result_for(message, wait=0.3)
        else:
            m = sp._last["result"] if time.time() - sp._last["at"] <= VOICE_TTL else None
        if not m:
            return None
        if m.get("segments"):
            return {"kind": "multi", "name": None, "score": m.get("score")}
        if m.get("name"):
            return {"kind": "name", "name": m["name"], "score": m["score"]}
        return {"kind": "unknown", "name": None, "score": m.get("score")}
    except Exception:
        return None


def assess(message=None):
    """Fuse the live signals -> {posture, who, face, voice}. posture None = nothing known."""
    me = _owner()
    f = _sig.get("face")
    face = f if f and time.time() - f["at"] <= FACE_TTL else None
    v = _voice(message)
    fn = face["names"] if face else []
    fu = face["unknown"] if face else 0
    out = {"face": face, "voice": v, "who": None, "posture": None}

    if v and v["kind"] == "multi":
        out["posture"] = "multi"
    elif v and v["kind"] == "name" and v["name"] != me:
        out.update(posture="other_known", who=v["name"])
    elif v and v["kind"] == "name":                       # voice says owner
        out["who"] = me
        out["posture"] = "owner_plus_others" if fu else ("owner_confirmed" if me in fn else "owner_likely")
    elif v and v["kind"] == "unknown":
        out["posture"] = "conflict" if (me in fn and not fu and len(fn) == 1) else "unknown"
    elif fn or fu:                                        # no voice signal: camera only
        others = [n for n in fn if n != me]
        if me in fn and not fu and not others:
            out.update(posture="owner_likely", who=me)
        elif me in fn:
            out.update(posture="owner_plus_others", who=me)
        elif others:
            out.update(posture="other_known", who=others[0])
        else:
            out["posture"] = "unknown"
    return out


def turn_hint(message):
    if not flag("IDENTITY_FUSION"):
        return ""
    try:
        a = assess(message)
    except Exception:
        return ""
    p, me = a["posture"], _owner()
    if p in (None, "owner_confirmed", "owner_likely"):
        return ""
    if p == "conflict":
        return (f"The camera sees {me} but the voice in this message does not match {me}'s. Someone else may be "
                f"speaking. Don't share {me}'s private details; if it matters, ask who's speaking.")
    if p == "owner_plus_others":
        return (f"{me} is here, but other people are also in view (not all recognised). Keep {me}'s private details, "
                "finances and messages out of spoken replies unless he clearly asks for them.")
    if p == "multi":
        return "More than one person spoke in this message; answer whoever addressed you and don't reveal private details."
    if p == "unknown":
        return (f"Nobody in view or earshot is recognised. Treat this as a stranger: be polite, don't reveal {me}'s "
                "private details or control the home, and offer to remember them if they introduce themselves.")
    if p == "other_known":
        who = a["who"]
        role = _role(who)
        tail = {"family": "A family member: be warm and open, but still not {me}'s finances or private messages.",
                "friend": "A friend: friendly, but no private details about {me} and no home control.",
                "guest": "A guest: polite and brief; nothing private, no home control."}.get(
            role, "Role not set: be warm but keep {me}'s private details and home control to {me} only.")
        return f"This sounds/looks like {who} (not {me}). " + tail.format(me=me)
    return ""


def _describe(a):
    me = _owner()
    f, v = a["face"], a["voice"]
    bits = []
    if f:
        seen = ", ".join(f["names"]) or "no one I know"
        bits.append(f"camera: {seen}" + (f" + {f['unknown']} unrecognised" if f["unknown"] else ""))
    else:
        bits.append("camera: nothing recent")
    if v:
        bits.append("voice: " + {"name": f"{v['name']} ({v['score']:.2f})", "unknown": "an unrecognised voice",
                                 "multi": "several voices"}[v["kind"]])
    else:
        bits.append("voice: no usable signal (no enrolled voice, or nothing recent)")
    verdict = {"owner_confirmed": f"{me}, confirmed by face and voice.",
               "owner_likely": f"Probably {me} (one signal, nothing contradicts it).",
               "owner_plus_others": f"{me} is here, with other people in view.",
               "conflict": f"Conflict: {me}'s face is in view but the voice isn't his.",
               "other_known": f"{a['who']} (not {me}), role: {_role(a['who'])}." if a["who"] else "",
               "unknown": "No one I recognise.", "multi": "More than one person spoke.",
               None: "I have no recent signal to go on."}[a["posture"]]
    return verdict + " (" + "; ".join(bits) + "). This is a soft signal, not proof."


def call(name, args):
    try:
        args = args or {}
        if name == "who_is_here":
            return {"status": "success", "output": _describe(assess(None))}
        if name == "set_person_role":
            nm = (args.get("name") or "").strip()
            role = (args.get("role") or "").strip().lower()
            if role not in ROLE_WORDS:
                return {"status": "error", "error": "role must be family, friend or guest"}
            if nm == _owner():
                return {"status": "error", "error": "the owner's role can't be changed"}
            ident = _D["speakers"]._D["identities"]() if _D.get("speakers") else {}
            if nm not in (ident or {}) and not _faces_know(nm):
                return {"status": "success", "output": f"I don't have {nm} enrolled by face or voice yet, so I won't set a role."}
            roles = _roles()
            roles[nm] = role
            _D["memory"].remember("long_term", ROLES_KEY, roles)
            return {"status": "success", "output": f"OK, I'll treat {nm} as {role}."}
        return {"status": "error", "error": f"unknown tool {name}"}
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}


def _faces_know(nm):
    try:
        return nm in (_D["memory"].recall("long_term", "face_identities") or {})
    except Exception:
        return False
