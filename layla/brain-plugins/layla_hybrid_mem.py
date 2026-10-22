"""Layla hybrid memory -- Task 1, capability #6 (hybrid memory + self-evolving RAG).

Builds on #1 (day episodes). Two halves:

1. SELF-EVOLVING: every night (after the episodic pass) the day's episode is
   distilled into durable facts. Each candidate is compared with the closest
   existing facts and the LLM decides ADD / UPDATE / NOOP -- so knowledge is
   corrected in place instead of piling up contradictions. Old values are kept
   as history (nothing is silently lost). Facts that get recalled are
   reinforced; facts never used for 180 days and low-confidence are marked
   stale (down-ranked, never deleted).

2. HYBRID RETRIEVAL: deep_recall(query) fuses keyword (BM25-lite) and vector
   search over facts, day episodes, saved documents and the entity graph with
   reciprocal-rank fusion -- one tool that finds things by word OR by meaning.

Kill switch: HYBRID_MEM=0. Never raises into the caller.
"""
import hashlib
import math
import re
import threading
import time
import datetime as _dt
from collections import Counter

from layla_plugin_util import IST, S, flag, llm_json, now_ist, tool

USAGE_KEY = "facts:usage"
HIST_PREFIX = "facts:history:"
LOG_KEY = "hybrid:log"
DONE_KEY = "hybrid:distilled_days"
DISTILL_HOUR_IST = 4
MAX_NEW_PER_DAY = 12
STALE_DAYS = 180

_D = {}   # memory, qdrant, facts_collection, embed, remember_fact, epi, kb_search, graph_query
_cache = {"at": 0.0, "facts": []}
_lock = threading.Lock()

TOOLS = [tool("deep_recall",
              "Search EVERYTHING you remember about the owner at once -- stored facts, preferences, past days, "
              "saved documents and people/relationships -- by exact words AND by meaning. Use it when a "
              "question depends on his past, plans, people, projects or preferences and a single fact "
              "lookup isn't enough ('what did we decide about the Tesla', 'what do you know about my mom's "
              "health', 'remind me what I was building last week').",
              {"query": S}, ["query"])]
NAMES = {"deep_recall"}

_DISTILL = """You maintain Avishkar's long-term memory. From one day's summary, extract DURABLE facts worth
remembering for months (preferences, people and relationships, ongoing projects, plans and decisions,
health routines he shared, important dates). Skip small talk, one-off device commands and anything
transient. Return ONLY JSON: {"facts": [{"key": "short_snake_case_topic", "value": "one plain sentence",
"confidence": 0.0-1.0}]}. At most 8 facts. Never invent anything not in the text.
Do NOT store: whether a device was on/off at some moment, the fact that he asked a question (e.g. asked the
time), what the assistant can do, one-off commands, or obvious things (that the assistant is Layla). Store only
what would still be true and useful about HIM in a month."""

# keys that are almost always transient junk ("ceiling_light_status", "time_inquiry", "tool_inventory_check" ...)
_JUNK_KEY_RE = re.compile(r"(_status|_inquiry|_query|_check|_request|_command|_control)$|assistant|layla", re.I)

_RESOLVE = """You reconcile new candidate memories with existing ones. For each candidate you get the closest
existing facts. Decide: "ADD" (genuinely new), "UPDATE" (same topic, new info supersedes or extends an
existing fact -- give the existing key and the merged value), or "NOOP" (already known).
Return ONLY JSON: {"ops": [{"i": <candidate index>, "op": "ADD|UPDATE|NOOP", "key": "...", "value": "..."}]}."""


def init(**deps):
    _D.update(deps)


def _mem():
    return _D["memory"]


# ---------------- facts index (keyword side) ----------------
def _all_facts(max_age=600):
    if time.time() - _cache["at"] < max_age and _cache["facts"]:
        return _cache["facts"]
    out, nxt = [], None
    try:
        while True:
            pts, nxt = _D["qdrant"].scroll(_D["facts_collection"], limit=256, offset=nxt,
                                           with_payload=True, with_vectors=False)
            out += [{"key": p.payload.get("key", ""), "value": str(p.payload.get("value", ""))} for p in pts]
            if not nxt or len(out) > 5000:
                break
    except Exception as e:
        print(f"[hybrid] fact scroll failed: {type(e).__name__}", flush=True)
    _cache.update(at=time.time(), facts=out)
    return out


_TOK = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "of", "to", "and", "or", "is", "are", "was", "were", "i", "my", "me", "you", "your",
         "what", "do", "did", "we", "about", "in", "on", "for", "with", "that", "this", "it", "know", "remember"}


def _stem(w):
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def _toks(t):
    return [_stem(w) for w in _TOK.findall((t or "").lower().replace("_", " ")) if w not in _STOP]


def _bm25(query, docs, k1=1.4, b=0.75):
    q = set(_toks(query))
    if not q or not docs:
        return []
    toks = [_toks(d) for d in docs]
    avg = sum(len(t) for t in toks) / max(1, len(toks))
    df = Counter(w for t in toks for w in set(t))
    N = len(docs)
    scores = []
    for i, t in enumerate(toks):
        tf = Counter(t)
        s = 0.0
        for w in q:
            if tf[w]:
                idf = math.log(1 + (N - df[w] + 0.5) / (df[w] + 0.5))
                s += idf * tf[w] * (k1 + 1) / (tf[w] + k1 * (1 - b + b * len(t) / max(avg, 1)))
        if s > 0:
            scores.append((i, s))
    return sorted(scores, key=lambda x: -x[1])


# ---------------- hybrid retrieval ----------------
def deep_recall(query, k=8):
    if not (query or "").strip():
        return "Tell me what to look for."
    usage = _mem().recall("long_term", USAGE_KEY) or {}
    ranked = {}   # id -> {"text":..., "ranks":[...]}

    def add(kind, ident, text, rank, weight=1.0):
        e = ranked.setdefault(f"{kind}:{ident}", {"kind": kind, "text": text, "rrf": 0.0, "key": ident})
        e["rrf"] += weight / (60 + rank)

    facts = _all_facts()
    for r, (i, _) in enumerate(_bm25(query, [f"{f['key']} {f['value']}" for f in facts])[:10]):
        f = facts[i]
        add("fact", f["key"], f"{f['key'].replace('_', ' ')}: {f['value']}", r)
    try:
        vec = _D["embed"](query)
        hits = _D["qdrant"].query_points(_D["facts_collection"], query=vec, limit=10).points
        for r, h in enumerate([h for h in hits if h.score >= 0.6]):
            add("fact", h.payload.get("key", ""), f"{str(h.payload.get('key','')).replace('_', ' ')}: {h.payload.get('value', '')}", r, 1.2)
    except Exception:
        pass
    epi = _D.get("epi")
    if epi is not None:
        try:
            for r, h in enumerate(epi.semantic_day_recall(query, k=4, min_score=0.5)):
                add("day", h["date"], f"[{h['date']}] {h['summary']}", r)
            idx = sorted(epi._index())
            days = [(d, (epi.get_day(d) or {})) for d in idx[-120:]]
            docs = [f"{d} {e.get('summary', '')} {' '.join(e.get('topics', []))} {' '.join(e.get('people', []))}" for d, e in days]
            for r, (i, _) in enumerate(_bm25(query, docs)[:4]):
                d, e = days[i]
                add("day", d, f"[{d}] {e.get('summary', '')}", r)
        except Exception:
            pass
    try:
        kb = _D["kb_search"](query) if _D.get("kb_search") else ""
        if kb and not str(kb).lower().startswith(("nothing", "no ")):
            add("doc", hashlib.md5(kb[:200].encode()).hexdigest()[:8], f"[saved document] {kb[:400]}", 0, 0.8)
    except Exception:
        pass
    for name in set(re.findall(r"\b[A-Z][a-z]{2,}\b", query or "")):
        try:
            rel = _D["graph_query"](name) if _D.get("graph_query") else ""
            if rel and "no " not in str(rel)[:15].lower():
                add("link", name, f"[relations of {name}] {str(rel)[:300]}", 0, 0.9)
        except Exception:
            pass
    if not ranked:
        return "I don't find anything about that in my memory."
    for e in ranked.values():
        if e["kind"] == "fact":
            u = usage.get(e["key"], {})
            if u.get("stale"):
                e["rrf"] *= 0.5
            e["rrf"] *= 1 + min(0.3, 0.03 * u.get("n", 0))
    top = sorted(ranked.values(), key=lambda e: -e["rrf"])[:k]
    now = time.time()
    for e in top:
        if e["kind"] == "fact" and e["key"]:
            u = usage.setdefault(e["key"], {"n": 0})
            u["n"] = u.get("n", 0) + 1
            u["last"] = now
            u.pop("stale", None)
    _mem().remember("long_term", USAGE_KEY, usage)
    return "From my memory (facts, days, documents, people -- best matches first):\n" + "\n".join(
        f"- {e['text']}" for e in top)


# ---------------- self-evolving distillation ----------------
def distill_day(date, force=False):
    with _lock:
        done = set(_mem().recall("long_term", DONE_KEY) or [])
        if date in done and not force:
            return "already"
        epi = _D.get("epi")
        ep = epi.get_day(date) if epi is not None else None
        if not ep or not ep.get("summary"):
            return "no-episode"
        text = (f"DATE {date}\nSUMMARY: {ep['summary']}\nTOPICS: {', '.join(ep.get('topics', []))}\n"
                f"PEOPLE: {', '.join(ep.get('people', []))}\nOPEN LOOPS: {'; '.join(ep.get('open_loops', []))}")
        cands = [c for c in (llm_json(_DISTILL, text).get("facts") or []) if c.get("key") and c.get("value")]
        cands = [c for c in cands if float(c.get("confidence", 0.7)) >= 0.75
                 and not _JUNK_KEY_RE.search(str(c.get("key", "")))][:8]
        if not cands:
            done.add(date)
            _mem().remember("long_term", DONE_KEY, sorted(done)[-400:])
            return "nothing-durable"
        blocks = []
        for i, c in enumerate(cands):
            near = []
            try:
                vec = _D["embed"](f"{c['key']}: {c['value']}")
                for h in _D["qdrant"].query_points(_D["facts_collection"], query=vec, limit=3).points:
                    if h.score >= 0.7:
                        near.append(f"  existing key={h.payload.get('key')} value={h.payload.get('value')} (sim {h.score:.2f})")
            except Exception:
                pass
            blocks.append(f"[{i}] candidate key={c['key']} value={c['value']}\n" + ("\n".join(near) or "  (no close existing facts)"))
        ops = llm_json(_RESOLVE, "\n".join(blocks), max_tokens=900).get("ops") or []
        applied = []
        for op in ops[:MAX_NEW_PER_DAY]:
            kind = str(op.get("op", "")).upper()
            key = re.sub(r"[^a-z0-9_]+", "_", str(op.get("key", "")).lower()).strip("_")[:60]
            val = str(op.get("value", "")).strip()
            if kind not in ("ADD", "UPDATE") or not key or not val:
                continue
            if kind == "UPDATE":
                try:
                    old = _D["recall_fact"](key)
                    if old:
                        h = _mem().recall("long_term", HIST_PREFIX + key) or []
                        h.append({"value": old, "replaced_at": time.time(), "by_day": date})
                        _mem().remember("long_term", HIST_PREFIX + key, h[-10:])
                except Exception:
                    pass
            _D["remember_fact"](key, val)
            applied.append(f"{kind} {key}")
        done.add(date)
        _mem().remember("long_term", DONE_KEY, sorted(done)[-400:])
        log = _mem().recall("long_term", LOG_KEY) or []
        log.append({"at": time.time(), "day": date, "applied": applied})
        _mem().remember("long_term", LOG_KEY, log[-200:])
        _cache["at"] = 0
        return f"ok: {', '.join(applied) or 'all known already'}"


def mark_stale():
    usage = _mem().recall("long_term", USAGE_KEY) or {}
    cut = time.time() - STALE_DAYS * 86400
    n = 0
    for f in _all_facts(0):
        u = usage.setdefault(f["key"], {"n": 0, "first_seen": time.time()})
        last = u.get("last", u.get("first_seen", time.time()))
        if last < cut and not u.get("stale"):
            u["stale"] = True
            n += 1
    _mem().remember("long_term", USAGE_KEY, usage)
    return n


def _loop():
    time.sleep(300)
    try:  # catch-up for the days #1 already consolidated
        epi = _D.get("epi")
        for d in (sorted(epi._index())[-14:] if epi is not None else []):
            print(f"[hybrid] distill {d}: {distill_day(d)}", flush=True)
            time.sleep(2)
    except Exception as e:
        print(f"[hybrid] catch-up failed: {type(e).__name__}: {e}", flush=True)
    last = None
    while True:
        try:
            now = now_ist()
            if flag("HYBRID_MEM") and now.hour >= DISTILL_HOUR_IST and last != now.date():
                y = (now.date() - _dt.timedelta(days=1)).isoformat()
                print(f"[hybrid] nightly {y}: {distill_day(y)}; stale marked: {mark_stale()}", flush=True)
                last = now.date()
        except Exception as e:
            print(f"[hybrid] nightly failed: {type(e).__name__}: {e}", flush=True)
        time.sleep(1800)


def start():
    if flag("HYBRID_MEM"):
        threading.Thread(target=_loop, daemon=True, name="hybrid-mem").start()


def call(name, args):
    try:
        if not flag("HYBRID_MEM"):
            return {"status": "error", "error": "hybrid memory is switched off"}
        if name == "deep_recall":
            return {"status": "success", "output": deep_recall((args or {}).get("query", ""))}
        return {"status": "error", "error": f"unknown tool {name}"}
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
