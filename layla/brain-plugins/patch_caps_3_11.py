"""Wires Task-1 capability plugins #3 #5 #6 #8 #9 #11 (+ shared approvals) into
layla_service.py. #10 (computer use) is deliberately NOT wired here -- held
for the owner's decision. Anchored, idempotent, fails loudly on a bad anchor."""
import sys
p = "/opt/layla/layla_service.py"
s = open(p, encoding="utf-8").read()
if "_CAP_PLUGINS" in s:
    print("already patched"); sys.exit(0)

def rep(old, new):
    global s
    assert s.count(old) == 1, f"anchor count {s.count(old)} for {old[:70]!r}"
    s = s.replace(old, new, 1)

# 1. import + register tools/scopes early (before scope patterns + _TOOL_NAMES are built)
rep('    print(f"[vision memory] not loaded: {_e}", flush=True)\n',
    '    print(f"[vision memory] not loaded: {_e}", flush=True)\n'
    '# Task 1 capability plugins (#3 affect, #8 speakers, #6 hybrid memory, #5 ambient,\n'
    '# #9 telemetry, #11 social + shared approvals). Each has its own kill switch in .env.\n'
    '_CAP_PLUGINS = {}\n'
    'for _modname, _cat in (("layla_affect", "affect"), ("layla_speakers", "speakers"),\n'
    '                       ("layla_hybrid_mem", None), ("layla_ambient", "ambient"),\n'
    '                       ("layla_telemetry", "telemetry"), ("layla_approvals", None),\n'
    '                       ("layla_social", "social")):\n'
    '    try:\n'
    '        _m = __import__(_modname)\n'
    '        _have = {t["function"]["name"] for t in TOOLS}\n'
    '        TOOLS.extend(t for t in _m.TOOLS if t["function"]["name"] not in _have)\n'
    '        if _cat and getattr(_m, "KEYWORDS", None):\n'
    '            _TOOL_CATEGORIES[_cat] = set(_m.NAMES)\n'
    '            _CATEGORY_KEYWORDS[_cat] = tuple(_m.KEYWORDS)\n'
    '        _CAP_PLUGINS[_modname] = _m\n'
    '    except Exception as _e:\n'
    '        print(f"[caps] {_modname} not loaded: {_e}", flush=True)\n')

# 2. dispatch
rep('        if _VM is not None and name in _VM.NAMES:\n            return _VM.call(name, args)\n',
    '        if _VM is not None and name in _VM.NAMES:\n            return _VM.call(name, args)\n'
    '        for _cm in _CAP_PLUGINS.values():\n'
    '            if name in _cm.NAMES:\n'
    '                return _cm.call(name, args)\n')

# 3. per-message hints (affect -> empathy guidance, speakers -> who is talking)
rep('    _tone_reminder = {"role": "system", "content": " ".join(_reminder_bits)}\n',
    '    for _cm in list(_CAP_PLUGINS.values()):\n'
    '        _th = getattr(_cm, "turn_hint", None)\n'
    '        if _th is not None:\n'
    '            try:\n'
    '                _h = _th(message)\n'
    '                if _h:\n'
    '                    _reminder_bits.append(_h)\n'
    '            except Exception:\n'
    '                pass\n'
    '    _tone_reminder = {"role": "system", "content": " ".join(_reminder_bits)}\n')

# 4. /ask post-hooks: strategy loop, listening face, activity clock
rep('                result = ask(m)\n',
    '                result = ask(m)\n'
    '                try:\n'
    '                    if isinstance(result, dict):\n'
    '                        _ca = _CAP_PLUGINS.get("layla_affect")\n'
    '                        if _ca is not None:\n'
    '                            _ca.after_reply(result.get("tone"))\n'
    '                            result["face"] = _ca.face_for_listening()\n'
    '                        _cb = _CAP_PLUGINS.get("layla_ambient")\n'
    '                        if _cb is not None:\n'
    '                            _cb.note_activity()\n'
    '                except Exception:\n'
    '                    pass\n')

# 5. /stt audio hooks (background threads; never delay the transcript) + new POST routes
rep('''        if path == "/stt":
            try:
                return self._json(200, {"text": stt_transcribe(data.get("audio", ""))})''',
'''        if path == "/telemetry/ingest":
            _ct = _CAP_PLUGINS.get("layla_telemetry")
            if _ct is None:
                return self._json(404, {"error": "not found"})
            return _ct.handle(self, data, _is_owner(self))
        if path == "/approval/decide":
            _cap = _CAP_PLUGINS.get("layla_approvals")
            if _cap is None:
                return self._json(404, {"error": "not found"})
            threading.Thread(target=_cap.decide, args=(str(data.get("id", "")), bool(data.get("allow")), "card"),
                             daemon=True).start()
            return self._json(200, {"ok": True})
        if path == "/stt":
            try:
                _stt_text = stt_transcribe(data.get("audio", ""))
                if _stt_text:
                    for _hk in ("layla_affect", "layla_speakers"):
                        _cm = _CAP_PLUGINS.get(_hk)
                        if _cm is not None:
                            try:
                                _cm.observe_audio(data.get("audio", ""), _stt_text)
                            except Exception:
                                pass
                return self._json(200, {"text": _stt_text})''')
rep('"/recognize_voice", "/stt"}', '"/recognize_voice", "/stt", "/approval/decide"}')

# 6. GET /approval/pending (owner only)
rep('_PROTECTED_GET = {"/ask", "/state",', '_PROTECTED_GET = {"/approval/pending", "/ask", "/state",')
rep('        if u.path == "/app" or u.path == "/index.html":\n',
    '        if u.path == "/approval/pending":\n'
    '            _cap = _CAP_PLUGINS.get("layla_approvals")\n'
    '            return self._json(200, _cap.pending_list() if _cap is not None else [])\n'
    '        if u.path == "/app" or u.path == "/index.html":\n')

# 7. late init (everything they depend on exists by now) + background loops
rep('''    _EPI = None
    print(f"[episodic] not loaded: {_epi_e}", flush=True)
''',
'''    _EPI = None
    print(f"[episodic] not loaded: {_epi_e}", flush=True)

def _plugin_log_said(text):
    """A line Layla said on her own (ambient/social) joins her history + archive."""
    try:
        hist = _memory.recall("episodic", CONV_KEY) or []
        hist.append({"role": "assistant", "content": text})
        _memory.remember("episodic", CONV_KEY, hist[-40:])
        _archive_turn("assistant", text)
    except Exception:
        pass

def _cap_init(modname, start=False, **deps):
    _cm = _CAP_PLUGINS.get(modname)
    if _cm is None:
        return
    try:
        _cm.init(**deps)
        if start and hasattr(_cm, "start"):
            _cm.start()
    except Exception as _ce:
        print(f"[caps] {modname} init failed: {_ce}", flush=True)

_cap_init("layla_approvals", push=push_event)
_cap_init("layla_affect", memory=_memory, text_estimator=_estimate_emotional_state)
_cap_init("layla_speakers", memory=_memory, embed_b64=_voice_embed_from_b64, identities=_voice_identities_load,
          cosine=globals().get("_voice_cosine"), threshold=VOICE_MATCH_THRESHOLD,
          available=VOICE_REC_AVAILABLE, enroll=enroll_voice_from_audio)
_cap_init("layla_telemetry")
_cap_init("layla_hybrid_mem", start=True, memory=_memory, qdrant=_qdrant, facts_collection=FACTS_COLLECTION,
          embed=_gemini_embed,
          remember_fact=lambda k, v: execute_tool("remember_fact", {"key": k, "value": v}),
          recall_fact=lambda k: (lambda o: None if o in (None, "", "no memory of that") else o)(
              (execute_tool("recall_fact", {"key": k}) or {}).get("output")),
          epi=_EPI, kb_search=search_knowledge_base, graph_query=query_entity_relations)
_cap_init("layla_ambient", start=True, memory=_memory, push=push_event,
          screens_open=lambda: len(_sse_clients) > 0, epi=_EPI,
          affect=_CAP_PLUGINS.get("layla_affect"), telemetry=_CAP_PLUGINS.get("layla_telemetry"),
          log_said=_plugin_log_said)
_cap_init("layla_social", start=True, memory=_memory, execute_tool=lambda n, a: execute_tool(n, a),
          approvals=_CAP_PLUGINS.get("layla_approvals"), push=push_event, log_said=_plugin_log_said)
''')

open(p, "w", encoding="utf-8").write(s)
print("patched")
