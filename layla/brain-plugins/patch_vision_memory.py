import sys
p = "/opt/layla/layla_service.py"
s = open(p, encoding="utf-8").read()
if "layla_vision_memory" in s:
    print("already patched"); sys.exit(0)

def rep(old, new):
    global s
    assert s.count(old) == 1, f"anchor count {s.count(old)} for {old[:60]!r}"
    s = s.replace(old, new, 1)

# 1. load module + register its tools/scope (same pattern as wae/layla_phone)
rep('    print(f"[WAE world awareness] not loaded: {_e}", flush=True)\n',
    '    print(f"[WAE world awareness] not loaded: {_e}", flush=True)\n'
    'try:\n'
    '    import layla_vision_memory as _VM\n'
    '    _VM.init(memory=_memory, groq_key=GROQ_KEY, model=VISION_MODEL, gemini_key=GEMINI_KEY,\n'
    '             fallback_model=VISION_FALLBACK_MODEL, fallback_url=VISION_FALLBACK_URL, see=see)\n'
    '    _have = {t["function"]["name"] for t in TOOLS}\n'
    '    TOOLS.extend(t for t in _VM.TOOLS if t["function"]["name"] not in _have)\n'
    '    _TOOL_CATEGORIES["visionmem"] = set(_VM.NAMES)\n'
    '    _CATEGORY_KEYWORDS["visionmem"] = _VM.KEYWORDS\n'
    '    _TOOL_CATEGORIES["vision"] |= set(_VM.NAMES)\n'
    'except Exception as _e:\n'
    '    _VM = None\n'
    '    print(f"[vision memory] not loaded: {_e}", flush=True)\n')

# 2. dispatch
rep('        if _WAE is not None and name in _WAE.NAMES:\n            return _WAE.call(name, args)\n',
    '        if _WAE is not None and name in _WAE.NAMES:\n            return _WAE.call(name, args)\n'
    '        if _VM is not None and name in _VM.NAMES:\n            return _VM.call(name, args)\n')

# 3. observe every explicit look (background, never delays the answer)
rep('                _reconcile_vision_answer(ans)  # close the loop: replace the "let me look" placeholder with what was actually seen\n',
    '                _reconcile_vision_answer(ans)  # close the loop: replace the "let me look" placeholder with what was actually seen\n'
    '                if _VM is not None: _VM.observe(image, "room webcam")\n')
rep('                ans = scan_room_from_image(image)\n                _reconcile_vision_answer(ans)\n',
    '                ans = scan_room_from_image(image)\n                _reconcile_vision_answer(ans)\n'
    '                if _VM is not None: _VM.observe(image, "room webcam")\n')
rep('            diag = scan_room_diagnostic(frame, source="room")\n            diag["capture_ms"]',
    '            diag = scan_room_diagnostic(frame, source="room")\n'
    '            if _VM is not None: _VM.observe(frame, "TV camera")\n'
    '            diag["capture_ms"]')

# 4. short-term visual continuity in her context
rep('''                parts.append(_rd)
    except Exception:
        pass
    return " | ".join(parts)''',
'''                parts.append(_rd)
    except Exception:
        pass
    try:
        if globals().get("_VM") is not None:
            _vl = _VM.context_line()
            if _vl:
                parts.append(_vl)
    except Exception:
        pass
    return " | ".join(parts)''')

open(p, "w", encoding="utf-8").write(s)
print("patched")
