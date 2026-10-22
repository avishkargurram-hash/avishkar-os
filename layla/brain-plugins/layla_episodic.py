"""Layla episodic memory -- Task 1, capabilities #1 (long-term memory) and #6 (hybrid recall).

* Nightly consolidation: each IST day's conversation turns (conv:archive) are
  condensed by the LLM into one episode {summary, topics, people, mood,
  open_loops}, stored durably (long_term "memday:<date>") and embedded into
  Qdrant collection "layla_episodes".
* Graceful forgetting: raw turns still roll off conv:archive at its cap, but a
  day's gist survives forever -- lossy compression, like human memory.
* Continuity: recent_days_context() feeds the last few days into her context.
* Hybrid recall: semantic_day_recall() finds days by MEANING, merged with the
  existing keyword search in recall_conversation().

Never raises into the caller; every public function degrades to "" / [].
"""
import datetime as _dt
import hashlib
import json
import os
import re
import threading
import time
import urllib.request

EPISODES = "layla_episodes"
DIM = 3072
DAY_PREFIX = "memday:"
INDEX_KEY = "memday:__index__"
MIN_TURNS = 2
MIN_SCORE = 0.55
BACKFILL_DAYS = 90
CONSOLIDATE_HOUR_IST = 3

_D = {}  # injected deps: memory, embed, qdrant, qmodels, archive_key, tz
_lock = threading.Lock()

_PROMPT = """You condense one day of conversation between Avishkar and his assistant Layla into a durable memory.
Return ONLY JSON:
{"summary": "3-6 plain sentences: what happened, what he worked on or felt, decisions made, anything he asked her to remember",
 "topics": ["3-8 short topic tags"],
 "people": ["names of people mentioned, if any"],
 "mood": "one or two words for his overall mood that day, or \\"unknown\\"",
 "open_loops": ["things left unfinished or promised for later, if any"]}
Rules: only facts present in the transcript; never invent; write the summary in third person about Avishkar; keep private details factual and brief."""


def init(**deps):
    _D.update(deps)
    try:
        q, m = _D["qdrant"], _D["qmodels"]
        try:
            q.get_collection(EPISODES)
        except Exception:
            q.create_collection(collection_name=EPISODES,
                                vectors_config=m.VectorParams(size=DIM, distance=m.Distance.COSINE))
    except Exception as e:
        print(f"[episodic] qdrant init skipped: {e}", flush=True)


def _llm(system, user, max_tokens=700):
    key = os.environ.get("CEREBRAS_API_KEY", "")
    if not key:
        raise RuntimeError("no CEREBRAS_API_KEY")
    body = {"model": os.environ.get("EPISODIC_MODEL", "gpt-oss-120b"),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": max_tokens, "temperature": 0.2, "reasoning_effort": "low"}
    req = urllib.request.Request("https://api.cerebras.ai/v1/chat/completions",
                                 data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                          "User-Agent": "layla/1.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        d = json.loads(r.read())
    return (d["choices"][0]["message"].get("content") or "").strip()


def _parse_json(raw):
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    m = re.search(r"\{.*\}", raw, re.S)
    return json.loads(m.group(0) if m else raw)


def _day_of(ts):
    return _dt.datetime.fromtimestamp(ts, _D["tz"]).date().isoformat()


def _archive():
    try:
        return _D["memory"].recall("long_term", _D["archive_key"]) or []
    except Exception:
        return []


def _index():
    try:
        return set(_D["memory"].recall("long_term", INDEX_KEY) or [])
    except Exception:
        return set()


def get_day(date):
    try:
        return _D["memory"].recall("long_term", DAY_PREFIX + date)
    except Exception:
        return None


def build_episode(date, turns):
    """Pure: turns -> episode dict (LLM call). No storage. Used by tests too."""
    lines = []
    for t in turns:
        who = "Avishkar" if t.get("role") == "user" else "Layla"
        when = _dt.datetime.fromtimestamp(t.get("at", 0), _D["tz"]).strftime("%H:%M")
        lines.append(f"[{when}] {who}: {str(t.get('content', ''))[:600]}")
    transcript = "\n".join(lines)[-12000:]
    data = _parse_json(_llm(_PROMPT, f"DATE: {date}\nTRANSCRIPT:\n{transcript}"))
    return {
        "date": date,
        "summary": str(data.get("summary", "")).strip(),
        "topics": [str(x) for x in (data.get("topics") or [])][:8],
        "people": [str(x) for x in (data.get("people") or [])
                   if str(x).strip().lower() not in ("avishkar", "layla", "assistant", "user")][:10],
        "mood": str(data.get("mood", "unknown")),
        "open_loops": [str(x) for x in (data.get("open_loops") or [])][:6],
        "turns": len(turns),
        "first_at": turns[0].get("at") if turns else None,
        "last_at": turns[-1].get("at") if turns else None,
        "created": time.time(),
    }


def consolidate_day(date, force=False):
    with _lock:
        if not force and get_day(date):
            return "exists"
        turns = [t for t in _archive() if isinstance(t, dict) and _day_of(t.get("at", 0)) == date]
        if len(turns) < MIN_TURNS:
            return "too-few-turns"
        ep = build_episode(date, turns)
        if not ep["summary"]:
            return "empty-summary"
        _D["memory"].remember("long_term", DAY_PREFIX + date, ep)
        idx = _index()
        idx.add(date)
        _D["memory"].remember("long_term", INDEX_KEY, sorted(idx))
        try:
            text = f"{date}: {ep['summary']} Topics: {', '.join(ep['topics'])}. People: {', '.join(ep['people'])}."
            vec = _D["embed"](text)
            pid = hashlib.sha256(("episode:" + date).encode()).hexdigest()[:32]
            _D["qdrant"].upsert(EPISODES, points=[_D["qmodels"].PointStruct(id=pid, vector=vec, payload={
                "date": date, "summary": ep["summary"], "topics": ep["topics"], "people": ep["people"],
                "mood": ep["mood"]})])
        except Exception as e:
            print(f"[episodic] embed skipped for {date} (episode still saved): {e}", flush=True)
        return "ok"


def backfill(max_days=BACKFILL_DAYS):
    today = _dt.datetime.now(_D["tz"]).date()
    days = sorted({_day_of(t.get("at", 0)) for t in _archive() if isinstance(t, dict)})
    done = {}
    for d in days:
        dd = _dt.date.fromisoformat(d)
        if dd >= today or (today - dd).days > max_days:
            continue
        try:
            done[d] = consolidate_day(d)
        except Exception as e:
            done[d] = f"error: {type(e).__name__}"
        time.sleep(1)
    return done


def recent_days_context(n=3, max_chars=900):
    try:
        idx = sorted(_index(), reverse=True)[:n]
        parts = []
        for d in idx:
            ep = get_day(d) or {}
            if ep.get("summary"):
                parts.append(f"{d}: {ep['summary']}")
        if not parts:
            return ""
        return ("Recent days with him (background continuity; mention only if it naturally fits): "
                + " || ".join(parts))[:max_chars]
    except Exception:
        return ""


def semantic_day_recall(query, k=3, min_score=MIN_SCORE):
    try:
        vec = _D["embed"](query)
        hits = _D["qdrant"].query_points(EPISODES, query=vec, limit=k).points
        return [{"date": h.payload.get("date"), "summary": h.payload.get("summary"),
                 "topics": h.payload.get("topics"), "score": h.score} for h in hits if h.score >= min_score]
    except Exception:
        return []


def recall_block(query, k=3):
    hits = semantic_day_recall(query, k)
    if not hits:
        return ""
    lines = [f"[{h['date']}] {h['summary']}" for h in hits]
    return "Days that match by meaning:\n" + "\n".join(lines)


def _loop():
    time.sleep(120)
    try:
        r = backfill()
        print(f"[episodic] backfill: {sum(1 for v in r.values() if v == 'ok')} new episodes "
              f"({len(r)} days checked)", flush=True)
    except Exception as e:
        print(f"[episodic] backfill failed: {e}", flush=True)
    last_run = None
    while True:
        try:
            now = _dt.datetime.now(_D["tz"])
            if now.hour >= CONSOLIDATE_HOUR_IST and last_run != now.date():
                y = (now.date() - _dt.timedelta(days=1)).isoformat()
                print(f"[episodic] nightly {y}: {consolidate_day(y)}", flush=True)
                last_run = now.date()
        except Exception as e:
            print(f"[episodic] nightly failed: {e}", flush=True)
        time.sleep(1800)


def start():
    threading.Thread(target=_loop, daemon=True, name="episodic").start()
