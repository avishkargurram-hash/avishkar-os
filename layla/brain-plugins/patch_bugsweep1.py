"""Bug sweep 1 (2026-10-12) for layla_service.py. Usage: python patch_bugsweep1.py [path]
Fixes found by the archive/journal audit:
  A. fake tool call written as text in the weather shape -- args-only {"query": ...} + {"results": [...]}
     -> recognised as web_search (so she REALLY searches) and the fake results are stripped
  B. final answer guard on /ask: strips any leftover tool/JSON blob + the "We need to call..." narration,
     and repairs the stored history so the junk never re-enters the context
  C. speech guard: code blocks, raw URLs and JSON are never read aloud; spoken text capped (~900 chars)
  D. STT: a language other than English/Telugu (e.g. "¿Hey, Laila?" read as Spanish) -> re-run as English
  E. always-on time hint was answering the time unprompted ("Is it?" -> "it's 9:58 PM") -> only when asked
  G. "what can you see WITH" (a capability question) no longer forces a camera look
  I. /app and its JS/CSS are served with Cache-Control: no-cache (stale tabs kept running old code)
Idempotent; every anchor asserted exactly once."""
import sys
p = sys.argv[1] if len(sys.argv) > 1 else "/opt/layla/layla_service.py"
s = open(p, encoding="utf-8").read()
if "_final_answer_guard" in s:
    print("already patched"); sys.exit(0)


def rep(old, new):
    global s
    assert s.count(old) == 1, f"anchor count {s.count(old)}: {old[:80]!r}"
    s = s.replace(old, new, 1)


# ---- A. scanner: args-only web_search + fake "results" blobs ----
rep('_PSEUDO_TOOLRESULT_KEYS = ("status", "output", "error")\n',
    '_PSEUDO_TOOLRESULT_KEYS = ("status", "output", "error", "results", "result", "data")\n'
    '_PSEUDO_WEB_HINT_RE = re.compile(r"\\b(web|search|internet|online|google|look(?:ed)?\\s+up|weather|news|latest)\\b", re.I)\n')
rep('''        name = next((obj[k] for k in _PSEUDO_TOOLCALL_NAME_KEYS
                     if isinstance(obj.get(k), str) and obj[k] in _TOOL_NAMES), None)
        if name:
            args = obj.get("arguments") or obj.get("args") or obj.get("parameters") or {}
''',
'''        name = next((obj[k] for k in _PSEUDO_TOOLCALL_NAME_KEYS
                     if isinstance(obj.get(k), str) and obj[k] in _TOOL_NAMES), None)
        _args_only = None
        # Arguments-only blob, e.g. 'We need to query web for X.{"query": "X"}' -- no tool name at all.
        # Only a plain search query, only when the text itself talks about searching the web.
        if (not name and isinstance(obj.get("query"), str) and set(obj) <= {"query", "max_results", "num_results", "count"}
                and "web_search" in _TOOL_NAMES and _PSEUDO_WEB_HINT_RE.search(text)):
            name, _args_only = "web_search", {"query": obj["query"][:300]}
        if name:
            args = _args_only if _args_only is not None else (obj.get("arguments") or obj.get("args") or obj.get("parameters") or {})
''')

# ---- B. final answer guard (helpers placed right after the scanner) ----
rep('def _strip_leading_json_blob(text):\n',
'''_LEAK_KEYS = {"query", "results", "result", "data", "items", "arguments", "args", "parameters", "action", "tool",
              "tool_name", "name", "function", "status", "output", "error", "title", "url", "snippet", "source"}
_ANALYSIS_LEAD_RE = re.compile(
    r"^\\s*(?:(?:we|i)\\s+(?:need|should|must|have)\\s+to|need\\s+to|let'?s)\\s+(?:call|query|use|search|look|check|run|invoke|fetch)\\b[^.\\n{]*[.\\n]?\\s*"
    r"|^\\s*the user (?:wants|asks|is asking)[^.\\n{]*[.\\n]?\\s*", re.I)

def _final_answer_guard(text):
    """Last line of defence before an answer is shown, spoken or stored: removes tool-call/result JSON the
    model wrote as prose and the planning sentence that came with it. Returns (clean_text, changed)."""
    if not text or "{" not in text:
        return text, False
    orig = text
    t, _rec = _scan_pseudo_tool_json(text)
    cuts = []
    for (a, b) in _find_json_spans(t):
        try:
            obj = json.loads(t[a:b])
        except Exception:
            continue
        if isinstance(obj, dict) and obj and set(obj) <= _LEAK_KEYS:
            cuts.append((a, b))
    for (a, b) in reversed(cuts):
        t = t[:a] + " " + t[b:]
    if t != orig:
        t = _ANALYSIS_LEAD_RE.sub("", t, count=1)
    t = re.sub(r"\\s{2,}", " ", t).strip()
    if not t:
        t = "Sorry, I got tangled up there. Could you ask me that once more?"
    return t, t != orig

def _strip_leading_json_blob(text):
''')
rep('''                result = ask(m)
                try:
                    if isinstance(result, dict):
                        _ca = _CAP_PLUGINS.get("layla_affect")
''',
'''                result = ask(m)
                try:
                    if isinstance(result, dict) and isinstance(result.get("answer"), str):
                        _ga, _gchanged = _final_answer_guard(result["answer"])
                        if _gchanged:
                            print(f"[guard] cleaned leaked tool text from answer ({len(result['answer'])}->{len(_ga)} chars)", flush=True)
                            _orig_answer, result["answer"] = result["answer"], _ga
                            _h = _memory.recall("episodic", CONV_KEY) or []
                            for _x in reversed(_h[-4:]):
                                if _x.get("role") == "assistant" and _x.get("content") == _orig_answer:
                                    _x["content"] = _ga
                                    _memory.remember("episodic", CONV_KEY, _h)
                                    break
                            _ar = _memory.recall("long_term", CONV_ARCHIVE_KEY) or []
                            for _x in reversed(_ar[-4:]):
                                if _x.get("role") == "assistant" and _x.get("content") == _orig_answer:
                                    _x["content"] = _ga
                                    _memory.remember("long_term", CONV_ARCHIVE_KEY, _ar)
                                    break
                except Exception as _ge:
                    print(f"[guard] skipped: {_ge}", flush=True)
                try:
                    if isinstance(result, dict):
                        _ca = _CAP_PLUGINS.get("layla_affect")
''')

# ---- C. speech guard ----
rep('''    t = _MD_LINK_RE.sub(r"\\1", text)        # [label](url) -> label (drop the URL, keep the words)
''',
'''    text = re.sub(r"```.*?(?:```|$)", " (I've put that on your screen.) ", text, flags=re.S)   # never read code aloud
    t = _MD_LINK_RE.sub(r"\\1", text)        # [label](url) -> label (drop the URL, keep the words)
''')
rep('''    t = _MD_BOLDITALIC_RE.sub("", t)
    return re.sub(r"\\n{2,}", ". ", t).strip()
''',
'''    t = _MD_BOLDITALIC_RE.sub("", t)
    return _speech_extra(re.sub(r"\\n{2,}", ". ", t).strip())

_SPEECH_MAX = 900

def _speech_extra(t):
    """Never speak raw URLs or JSON; keep spoken replies to ~900 chars (the screen shows everything)."""
    try:
        t = re.sub(r"https?://\\S+", "the link", t)
        if "{" in t:
            t = _final_answer_guard(t)[0]
        if len(t) > _SPEECH_MAX:
            cut = t[:_SPEECH_MAX]
            end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "), cut.rfind("\\u0964"))
            t = (cut[:end + 1] if end > 200 else cut) + " The rest is on your screen."
    except Exception:
        pass
    return t
''')

# ---- D. STT: only English or Telugu ----
rep('''        if lang in _STT_INDIC:
            _lang2, text2 = _stt_call(stt_model, "te", stt_prompt)
            if text2:
                text = text2
''',
'''        if lang in _STT_INDIC:
            _lang2, text2 = _stt_call(stt_model, "te", stt_prompt)
            if text2:
                text = text2
        elif lang and lang not in ("english", "en"):
            # e.g. a short "Hey Layla" detected as Spanish -> "¿Hey, Laila?"; he only speaks English/Telugu
            _lang3, text3 = _stt_call(stt_model, "en")
            if text3:
                text = text3
''')

# ---- E. time hint: answer only when asked ----
rep('" India time (IST, Asia/Kolkata). Answer any time/date question from this, in IST; "',
    '" India time (IST, Asia/Kolkata). Use this ONLY when he asks about the time, day or date (answer in IST, never another timezone); "')
rep('"never guess another timezone or date.")', '"otherwise do not bring up the time.")')

# ---- G. capability question is not a camera request ----
rep('    r"\\b(can you see me|do you see me|what do you see|what can you see|"\n',
    '    r"\\b(can you see me|do you see me|what do you see|what can you see(?!\\s+with)|"\n')

# ---- I. no stale /app tabs ----
rep('''        with open(path, "rb") as f:
            return self._bytes(200, f.read(), ct)
''',
'''        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "https://layla.tryvanta.in")
        if path.endswith((".html", ".js", ".css")):
            self.send_header("Cache-Control", "no-cache")   # a long-open tab must pick up a redeploy
        self.end_headers(); self.wfile.write(body)
        return None
''')

open(p, "w", encoding="utf-8").write(s)
print("bugsweep1 patched")
