"""Layla affect engine -- Task 1, capability #3 (emotional computing / empathy loop).

Signals (no face reading -- deliberately, see the 4b guardrail):
* VOICE prosody from the /stt WAV he just spoke: loudness, pitch level, pitch
  movement, speaking rate, pauses -- each compared to HIS OWN rolling
  baseline (z-scores), so a naturally loud or fast speaker isn't "stressed".
* TEXT: a small lexicon (English + common Tenglish) plus the brain's existing
  _estimate_emotional_state() cues.

Fused into valence (-1..1) x arousal (-1..1) -> a label, smoothed across turns
(mood decays back to neutral). The LOOP: after each reply we remember which
tone she used for which mood, and on his next message we score whether his
valence improved -- so over time guidance prefers what actually helps him.

Never a diagnosis; the hint tells her never to announce what she detected.
Kill switch: AFFECT=0. Never raises into the caller.
"""
import base64
import io
import math
import re
import threading
import time
import wave

import numpy as np

from layla_plugin_util import S, I, flag, fmt_ts, tool

STATE_KEY = "affect:state"
LOG_KEY = "affect:log"
BASE_KEY = "affect:baseline"
STATS_KEY = "affect:strategy_stats"
LOG_CAP = 1000
MIN_BASELINE_N = 8
HALF_LIFE_S = 45 * 60

_D = {}  # memory, text_estimator
_lock = threading.Lock()
_pending_audio = {"at": 0.0, "text": "", "feat": None}
_pending_reply = {"at": 0.0, "label": "", "valence": 0.0, "tone": ""}

FEATURES = ("energy_db", "f0_med", "f0_spread", "rate_wps", "pause_ratio")

_POS = {"happy", "great", "awesome", "love", "loved", "nice", "good", "glad", "excited", "amazing", "thanks",
        "thank", "yay", "finally", "perfect", "cool", "fantastic", "relieved", "proud", "super", "best",
        "santosham", "bagundi", "keka", "sooper", "mast", "hahaha", "haha", "lol"}
_NEG = {"sad", "tired", "exhausted", "angry", "upset", "annoyed", "frustrated", "stressed", "worried",
        "anxious", "hate", "bad", "terrible", "awful", "sick", "fail", "failed", "failing", "lonely", "hurt",
        "cry", "crying", "depressed", "scared", "afraid", "bored", "irritated", "done", "useless", "pain",
        "chiraaku", "chiraku", "kopam", "badha", "baadha", "bore", "tension", "headache", "worst", "fed"}
_NEGATORS = {"not", "no", "never", "dont", "don't", "isnt", "isn't", "wasnt", "wasn't", "cant", "can't"}
_EMO = {"😭": -0.8, "😢": -0.7, "😞": -0.6, "😡": -0.8, "😤": -0.6, "🙂": 0.3, "😊": 0.6, "😄": 0.7,
        "😂": 0.6, "❤": 0.7, "🥰": 0.8, "🔥": 0.5, "👍": 0.4}

TOOLS = [tool("get_mood_trend",
              "Summarise how the owner's mood has been over recent days, from the voice-tone and wording "
              "signals Layla has logged ('how have I been feeling this week', 'was I stressed lately'). "
              "This is an estimate from his voice/words, NEVER a diagnosis -- say so if relevant.",
              {"days": I}, [])]
NAMES = {"get_mood_trend"}
KEYWORDS = ("my mood", "how have i been", "been feeling", "mood trend", "was i stressed", "how was i")


def init(**deps):
    _D.update(deps)


def _mem():
    return _D["memory"]


# ---------------- voice prosody ----------------
def _decode(audio_b64):
    if audio_b64.startswith("data:") and "," in audio_b64[:80]:
        audio_b64 = audio_b64.split(",", 1)[1]
    w = wave.open(io.BytesIO(base64.b64decode(audio_b64)), "rb")
    sr = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    return x, sr


def prosody(audio_b64, transcript):
    x, sr = _decode(audio_b64)
    if len(x) < sr * 0.5:
        return None
    flen, hop = int(0.04 * sr), int(0.02 * sr)
    n = 1 + (len(x) - flen) // hop
    if n < 10:
        return None
    frames = np.stack([x[i * hop:i * hop + flen] for i in range(n)])
    rms = np.sqrt((frames ** 2).mean(axis=1) + 1e-12)
    gate = max(np.percentile(rms, 30) * 2.0, 0.008)
    voiced = rms > gate
    if voiced.sum() < 5:
        return None
    lo, hi = int(sr / 400), int(sr / 75)
    f0 = []
    win = np.hanning(flen).astype(np.float32)
    for fr in frames[voiced]:
        fr = (fr - fr.mean()) * win
        ac = np.correlate(fr, fr, mode="full")[flen - 1:]
        if ac[0] <= 0:
            continue
        seg = ac[lo:hi]
        if len(seg) == 0:
            continue
        k = int(np.argmax(seg))
        if seg[k] / ac[0] > 0.45:
            f0.append(sr / (lo + k))
    if len(f0) < 5:
        return None
    f0 = np.array(f0)
    semis = 12 * np.log2(f0 / np.median(f0))
    words = len(re.findall(r"\w+", transcript or ""))
    voiced_s = voiced.sum() * hop / sr
    return {
        "energy_db": float(20 * np.log10(np.median(rms[voiced]) + 1e-9)),
        "f0_med": float(12 * np.log2(np.median(f0) / 100.0)),       # semitones re 100 Hz
        "f0_spread": float(np.std(semis)),
        "rate_wps": float(words / max(voiced_s, 0.3)),
        "pause_ratio": float(1 - voiced.mean()),
    }


def _baseline_update(feat):
    b = _mem().recall("long_term", BASE_KEY) or {"n": 0}
    n = b.get("n", 0)
    z = {}
    for k in FEATURES:
        m, v = b.get(k + "_m"), b.get(k + "_v")
        if n >= MIN_BASELINE_N and m is not None:
            z[k] = (feat[k] - m) / math.sqrt(max(v, 1e-4))
        a = 1.0 / min(n + 1, 50)                      # running mean, then slow EMA
        if m is None:
            b[k + "_m"], b[k + "_v"] = feat[k], 1.0
        else:
            d = feat[k] - m
            b[k + "_m"] = m + a * d
            b[k + "_v"] = (1 - a) * (v + a * d * d)
    b["n"] = n + 1
    _mem().remember("long_term", BASE_KEY, b)
    return z if n >= MIN_BASELINE_N else None


def observe_audio(audio_b64, transcript):
    """/stt hook -- runs in its own thread, never delays the transcript."""
    if not flag("AFFECT"):
        return

    def _run():
        try:
            feat = prosody(audio_b64, transcript)
            if not feat:
                return
            with _lock:
                z = _baseline_update(feat)
            _pending_audio.update(at=time.time(), text=transcript or "", feat=feat, z=z)
        except Exception as e:
            print(f"[affect] prosody skipped: {type(e).__name__}", flush=True)
    threading.Thread(target=_run, daemon=True, name="affect-audio").start()


def _voice_for(message):
    if time.time() - _pending_audio["at"] > 30 or not _pending_audio.get("z"):
        return None
    a = set(re.findall(r"\w+", (_pending_audio["text"] or "").lower()))
    b = set(re.findall(r"\w+", (message or "").lower()))
    if not a or not b or len(a & b) / max(1, min(len(a), len(b))) < 0.6:
        return None
    return _pending_audio["z"]


# ---------------- text ----------------
def text_valence(message):
    words = re.findall(r"[a-z']+", (message or "").lower())
    score, hits = 0.0, 0
    for i, w in enumerate(words):
        s = 1 if w in _POS else -1 if w in _NEG else 0
        if s and any(p in _NEGATORS for p in words[max(0, i - 2):i]):
            s = -s * 0.7
        if s:
            score += s
            hits += 1
    for e, v in _EMO.items():
        if e in (message or ""):
            score += v * 1.5
            hits += 1
    val = math.tanh(score / 2.0)
    arousal = 0.0
    if "!" in (message or ""):
        arousal += 0.25
    caps = sum(1 for w in (message or "").split() if len(w) > 2 and w.isupper())
    arousal += min(0.4, caps * 0.2)
    est = {}
    try:
        est = _D["text_estimator"](message) or {}
    except Exception:
        pass
    if est.get("tone") == "tired":
        val, arousal, hits = min(val, -0.5), arousal - 0.4, hits + 1
    elif est.get("tone") == "frustrated":
        val, arousal, hits = min(val, -0.5), arousal + 0.4, hits + 1
    return val, arousal, min(1.0, hits / 2.0)


def _label(v, a):
    if abs(v) < 0.2 and abs(a) < 0.35:
        return "neutral"
    if v <= -0.2:
        return "stressed" if a > 0.25 else "low"
    if v >= 0.2:
        return "excited" if a > 0.35 else "content"
    return "energised" if a > 0 else "subdued"


# ---------------- fusion + loop ----------------
def assess(message):
    v_t, a_t, conf_t = text_valence(message)
    z = _voice_for(message)
    a_v, conf_v = 0.0, 0.0
    if z:
        a_v = math.tanh((z["energy_db"] + z["f0_med"] + 0.7 * z["f0_spread"] + 0.7 * z["rate_wps"]
                         - 0.5 * z["pause_ratio"]) / 4.0)
        conf_v = 0.5
    a = (a_t + 1.5 * a_v) / (1 + (1.5 if z else 0))
    v = v_t
    conf = min(1.0, conf_t + conf_v)
    # decayed blend with the running mood, so one stray word doesn't flip her --
    # but a clearly-worded message mostly speaks for itself
    st = _mem().recall("short_term", STATE_KEY) or {}
    if st:
        w = 0.5 ** ((time.time() - st.get("at", 0)) / HALF_LIFE_S) * 0.4 * (1 - 0.6 * conf)
        v = (1 - w) * v + w * st.get("valence", 0)
        a = (1 - w) * a + w * st.get("arousal", 0)
    lab = _label(v, a) if conf >= 0.25 else "neutral"
    out = {"valence": round(v, 3), "arousal": round(a, 3), "label": lab, "confidence": round(conf, 2),
           "voice": bool(z), "at": time.time()}
    _mem().remember("short_term", STATE_KEY, out)
    with _lock:
        log = _mem().recall("long_term", LOG_KEY) or []
        log.append({k: out[k] for k in ("valence", "arousal", "label", "confidence", "voice", "at")})
        _mem().remember("long_term", LOG_KEY, log[-LOG_CAP:])
    _score_last_strategy(v)
    return out


def _score_last_strategy(new_valence):
    p = dict(_pending_reply)
    if not p["tone"] or time.time() - p["at"] > 20 * 60 or p["label"] in ("", "neutral"):
        return
    _pending_reply["tone"] = ""
    stats = _mem().recall("long_term", STATS_KEY) or {}
    s = stats.setdefault(p["label"], {}).setdefault(p["tone"], {"n": 0, "gain": 0.0})
    s["gain"] = (s["gain"] * s["n"] + (new_valence - p["valence"])) / (s["n"] + 1)
    s["n"] += 1
    _mem().remember("long_term", STATS_KEY, stats)


def after_reply(tone):
    st = _mem().recall("short_term", STATE_KEY) or {}
    _pending_reply.update(at=time.time(), label=st.get("label", ""), valence=st.get("valence", 0.0),
                          tone=tone or "")


_GUIDE = {
    "stressed": "He sounds stressed or wound up. Be calm, clear and brief; give the single most useful next step; no jokes, no lists.",
    "low": "He sounds low or tired. Be soft and warm, keep it short, and offer one small caring thing (a check-in or one easy suggestion).",
    "excited": "He sounds upbeat and energised. Match his energy a little and share the moment.",
    "content": "He sounds relaxed and in a good mood -- easy, warm tone is right.",
    "energised": "His voice is more energetic than usual -- keep pace with him, be crisp.",
    "subdued": "His voice is quieter and slower than usual -- be gentle and unhurried.",
}


def turn_hint(message):
    if not flag("AFFECT"):
        return ""
    try:
        st = assess(message)
    except Exception as e:
        print(f"[affect] assess skipped: {type(e).__name__}", flush=True)
        return ""
    lab = st["label"]
    if lab == "neutral" or st["confidence"] < 0.25:
        return ""
    parts = [_GUIDE.get(lab, "")]
    best = None
    for tone, s in ((_mem().recall("long_term", STATS_KEY) or {}).get(lab) or {}).items():
        if s["n"] >= 3 and (best is None or s["gain"] > best[1]["gain"]):
            best = (tone, s)
    if best and best[1]["gain"] > 0:
        parts.append(f"When he has felt like this before, a {best[0]} reply helped most ({best[1]['n']} times).")
    parts.append("This is an estimate from his " + ("voice and words" if st["voice"] else "words")
                 + " -- never announce or label his emotion, just let it shape how you answer.")
    if needs_checkin():
        parts.append("He has seemed low for a while now; if it fits naturally, gently check in on him.")
    return " ".join(p for p in parts if p)


def needs_checkin(window_s=2 * 3600, k=3):
    log = _mem().recall("long_term", LOG_KEY) or []
    recent = [e for e in log if time.time() - e["at"] < window_s and e["confidence"] >= 0.25]
    return sum(1 for e in recent if e["label"] in ("stressed", "low")) >= k


def face_for_listening():
    st = _mem().recall("short_term", STATE_KEY) or {}
    if not st or time.time() - st.get("at", 0) > 600:
        return ""
    return {"stressed": "concerned", "low": "concerned", "subdued": "concerned",
            "excited": "smile", "content": "content", "energised": "smile"}.get(st.get("label"), "")


def mood_trend(days=7):
    log = _mem().recall("long_term", LOG_KEY) or []
    cut = time.time() - max(1, int(days or 7)) * 86400
    rec = [e for e in log if e["at"] >= cut and e["confidence"] >= 0.25]
    if not rec:
        return "I don't have enough mood signal for that period yet."
    from collections import Counter, defaultdict
    by_day = defaultdict(list)
    for e in rec:
        by_day[fmt_ts(e["at"])[:10]].append(e)
    lines = []
    for d, es in by_day.items():
        c = Counter(e["label"] for e in es).most_common(2)
        v = sum(e["valence"] for e in es) / len(es)
        lines.append(f"{d}: mostly {c[0][0]}" + (f", some {c[1][0]}" if len(c) > 1 else "") + f" (valence {v:+.2f})")
    return ("Estimated from his voice tone and wording (not a diagnosis): " + "; ".join(lines))


def call(name, args):
    try:
        if name == "get_mood_trend":
            return {"status": "success", "output": mood_trend((args or {}).get("days", 7))}
        return {"status": "error", "error": f"unknown tool {name}"}
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
