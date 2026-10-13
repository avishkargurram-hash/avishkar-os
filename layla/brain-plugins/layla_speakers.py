"""Layla speakers -- Task 1, capability #8 (speaker diarization + voiceprints).

Before: enroll_voice / recognize_voice existed but only ran when explicitly
asked. Now every utterance that reaches /stt is voice-matched in the
background (same local ReDimNet model, nothing leaves the VM):

* who said this turn -> a soft hint in her context (never a security
  decision: identity stays "uncertain" below threshold).
* unknown voices are clustered anonymously ("voice #2, heard 5 times") so a
  repeat guest can be named once and remembered (name_last_voice).
* long utterances (>= 6 s) are diarized: 2 s windows are matched separately
  and merged into speaker turns, so "two people talking" is detected.

Audio is never written beyond the model's own temp file (same as before);
the last utterance's audio is held in RAM only for 2 minutes, for naming.
Kill switch: SPEAKER_ID=0. Never raises into the caller.
"""
import base64
import io
import re
import threading
import time
import wave

import numpy as np

from layla_plugin_util import S, flag, fmt_ts, tool

ANON_KEY = "speakers:anon"
LOG_KEY = "speakers:log"
ANON_MATCH = 0.55
ANON_CAP = 10
AUDIO_TTL = 120
DIARIZE_MIN_S = 6.0
WIN_S, HOP_S, MAX_WIN = 2.0, 1.0, 8

_D = {}   # memory, embed_b64, identities, cosine, threshold, available, enroll
_busy = threading.Semaphore(1)
_last = {"at": 0.0, "done": threading.Event(), "text": "", "result": None, "audio": None}
_last["done"].set()

TOOLS = [
    tool("who_is_speaking",
         "Say who the most recent spoken message sounded like, by voice (enrolled voiceprints), and "
         "whether more than one person was talking. A voice match is a soft signal, not proof.",
         {}, []),
    tool("name_last_voice",
         "Give a name to the voice that spoke the most recent message, so you recognise it next time "
         "(e.g. after asking an unfamiliar voice who they are). Adds a reference clip for that name.",
         {"name": S}, ["name"]),
]
NAMES = {"who_is_speaking", "name_last_voice"}
KEYWORDS = ("who is speaking", "who's speaking", "who is talking", "who's talking", "whose voice",
            "who said that", "remember my voice", "my name is", "this is my", "two people")


def init(**deps):
    _D.update(deps)


def _wav_bytes(x, sr):
    buf = io.BytesIO()
    w = wave.open(buf, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    w.close()
    return base64.b64encode(buf.getvalue()).decode()


def _decode(audio_b64):
    if audio_b64.startswith("data:") and "," in audio_b64[:80]:
        audio_b64 = audio_b64.split(",", 1)[1]
    w = wave.open(io.BytesIO(base64.b64decode(audio_b64)), "rb")
    sr = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    return audio_b64, x, sr


def _match(vec):
    best, score = None, -1.0
    for name, embs in (_D["identities"]() or {}).items():
        for e in embs:
            s = float(_D["cosine"](vec, np.array(e, dtype=np.float32)))
            if s > score:
                best, score = name, s
    if best is not None and score >= _D["threshold"]:
        return {"name": best, "score": round(score, 3), "anon": None}
    anon = _D["memory"].recall("long_term", ANON_KEY) or []
    bi, bs = -1, -1.0
    for i, a in enumerate(anon):
        s = float(_D["cosine"](vec, np.array(a["c"], dtype=np.float32)))
        if s > bs:
            bi, bs = i, s
    if bi >= 0 and bs >= ANON_MATCH:
        a = anon[bi]
        c = np.array(a["c"], dtype=np.float32)
        a["c"] = ((c * a["n"] + vec) / (a["n"] + 1)).tolist()
        a["n"] += 1
        a["last"] = time.time()
        aid = a["id"]
    else:
        aid = max([a["id"] for a in anon] + [0]) + 1
        anon.append({"id": aid, "c": np.asarray(vec, dtype=np.float32).tolist(), "n": 1, "last": time.time()})
        anon = sorted(anon, key=lambda a: a["last"])[-ANON_CAP:]
    _D["memory"].remember("long_term", ANON_KEY, anon)
    heard = next((a["n"] for a in anon if a["id"] == aid), 1)
    return {"name": None, "score": round(score, 3), "closest": best, "anon": aid, "heard": heard}


def _label(m):
    return m["name"] or f"voice #{m['anon']}"


def _diarize(x, sr):
    win, hop = int(WIN_S * sr), int(HOP_S * sr)
    starts = list(range(0, max(1, len(x) - win + 1), hop))[:MAX_WIN]
    segs = []
    for s0 in starts:
        chunk = x[s0:s0 + win]
        if np.sqrt((chunk ** 2).mean()) < 0.01:
            continue
        m = _match_known_only(_D["embed_b64"](_wav_bytes(chunk, sr)))
        lab = m or "unknown"
        if segs and segs[-1]["speaker"] == lab:
            segs[-1]["end"] = round((s0 + win) / sr, 1)
        else:
            segs.append({"speaker": lab, "start": round(s0 / sr, 1), "end": round((s0 + win) / sr, 1)})
    return segs


def _match_known_only(vec):
    best, score = None, -1.0
    for name, embs in (_D["identities"]() or {}).items():
        for e in embs:
            s = float(_D["cosine"](vec, np.array(e, dtype=np.float32)))
            if s > score:
                best, score = name, s
    return best if score >= _D["threshold"] else None


def observe_audio(audio_b64, transcript):
    if not flag("SPEAKER_ID") or not _D.get("available") or not (_D["identities"]() or {}):
        return
    if not _busy.acquire(blocking=False):
        return                                  # one at a time on this 2-vCPU box; skip, never queue
    ev = threading.Event()
    _last.update(at=time.time(), done=ev, text=transcript or "", result=None, audio=None)

    def _run():
        try:
            b64, x, sr = _decode(audio_b64)
            dur = len(x) / float(sr)
            if dur < 1.0:
                return
            m = _match(_D["embed_b64"](b64))
            if dur >= DIARIZE_MIN_S and flag("DIARIZE_LONG"):
                segs = _diarize(x, sr)
                if len({s["speaker"] for s in segs}) > 1:
                    m["segments"] = segs
            _last.update(result=m, audio=b64)
            log = _D["memory"].recall("long_term", LOG_KEY) or []
            log.append({"at": time.time(), "who": _label(m), "score": m["score"], "text": (transcript or "")[:80],
                        "multi": bool(m.get("segments"))})
            _D["memory"].remember("long_term", LOG_KEY, log[-500:])
        except Exception as e:
            print(f"[speakers] skipped: {type(e).__name__}", flush=True)
        finally:
            ev.set()
            _busy.release()
    threading.Thread(target=_run, daemon=True, name="speakers").start()


def _result_for(message, wait=1.2):
    if time.time() - _last["at"] > 20:
        return None
    _last["done"].wait(wait)
    a = set(re.findall(r"\w+", (_last["text"] or "").lower()))
    b = set(re.findall(r"\w+", (message or "").lower()))
    if not a or not b or len(a & b) / max(1, min(len(a), len(b))) < 0.6:
        return None
    return _last["result"]


def turn_hint(message):
    if not flag("SPEAKER_ID"):
        return ""
    try:
        m = _result_for(message)
    except Exception:
        return ""
    if not m:
        return ""
    if m.get("segments"):
        who = ", ".join(dict.fromkeys(s["speaker"] for s in m["segments"]))
        return (f"By voice, more than one person spoke in this message ({who}). Answer the person addressing "
                "you; if it's unclear who asked, ask briefly.")
    if m["name"]:
        return f"By voice this message sounds like {m['name']} (similarity {m['score']:.2f}, a soft signal)."
    heard = m.get("heard", 1)
    return (f"This voice doesn't match anyone enrolled (an unfamiliar voice"
            + (f", heard {heard} times before" if heard > 1 else "") + "). Don't share private details "
            "about Avishkar with an unrecognised voice; if it fits, ask who's speaking and offer to remember "
            "them with name_last_voice.")


def call(name, args):
    try:
        args = args or {}
        if name == "who_is_speaking":
            m = _last["result"]
            if not m or time.time() - _last["at"] > 600:
                return {"status": "success", "output": "I haven't matched a spoken message in the last 10 minutes."}
            out = (f"Last spoken message ({fmt_ts(_last['at'])}) sounded like {m['name']} (similarity {m['score']:.2f})."
                   if m["name"] else
                   f"Last spoken message was an unrecognised voice (#{m['anon']}, heard {m.get('heard', 1)} times; "
                   f"closest enrolled was {m.get('closest')} at {m['score']:.2f}, below threshold).")
            if m.get("segments"):
                out += " Speaker turns: " + "; ".join(f"{s['speaker']} {s['start']}-{s['end']}s" for s in m["segments"])
            return {"status": "success", "output": out}
        if name == "name_last_voice":
            nm = (args.get("name") or "").strip()
            if not nm:
                return {"status": "error", "error": "need a name"}
            if not _last["audio"] or time.time() - _last["at"] > AUDIO_TTL:
                return {"status": "success", "output": "I no longer have that voice clip (I keep it only 2 minutes) -- "
                        "ask them to say a sentence and use enroll_voice instead."}
            m = _last["result"] or {}
            known = _D["identities"]() or {}
            if nm in known and m.get("name") != nm:
                return {"status": "success", "output": f"{nm} already has an enrolled voice and this clip doesn't match it, "
                        "so I won't add it under that name (that protects against impersonation)."}
            return {"status": "success", "output": _D["enroll"](_last["audio"], nm)}
        return {"status": "error", "error": f"unknown tool {name}"}
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
