import sys
p = "/opt/layla/layla_service.py"
s = open(p, encoding="utf-8").read()
if "layla_episodic" in s:
    print("already patched"); sys.exit(0)

def rep(old, new):
    global s
    assert s.count(old) == 1, f"anchor count {s.count(old)} for {old[:60]!r}"
    s = s.replace(old, new, 1)

# 1. load + start the episodic module after all its dependencies exist
rep("threading.Thread(target=_greeting_loop, daemon=True).start()\n",
    "threading.Thread(target=_greeting_loop, daemon=True).start()\n"
    "try:\n"
    "    import layla_episodic as _EPI\n"
    "    _EPI.init(memory=_memory, embed=_gemini_embed, qdrant=_qdrant, qmodels=_qmodels,\n"
    "              archive_key=CONV_ARCHIVE_KEY, tz=IST)\n"
    "    _EPI.start()\n"
    "except Exception as _epi_e:\n"
    "    _EPI = None\n"
    "    print(f\"[episodic] not loaded: {_epi_e}\", flush=True)\n")

# 2. hybrid recall: keyword hits + days that match by meaning
rep('''    if not scored:
        extra = (" in the last %d days" % days) if days else ""
        return {"status": "success", "output": f"I couldn't find anything in our archived conversations matching that{extra}."}''',
'''    _sem = ""
    try:
        if globals().get("_EPI") is not None and query:
            _sem = _EPI.recall_block(query)
    except Exception:
        _sem = ""
    if not scored:
        if _sem:
            return {"status": "success", "output": _sem}
        extra = (" in the last %d days" % days) if days else ""
        return {"status": "success", "output": f"I couldn't find anything in our archived conversations matching that{extra}."}''')
rep('''    return {"status": "success", "output": "From our earlier conversations:\\n" + "\\n".join(lines)}''',
'''    out = "From our earlier conversations:\\n" + "\\n".join(lines)
    if _sem:
        out += "\\n\\n" + _sem
    return {"status": "success", "output": out}''')

# 3. continuity: recent days in the always-on personal context
rep('''        print(f"[growth-context] skipped ({e})")
    return " | ".join(parts)''',
'''        print(f"[growth-context] skipped ({e})")
    try:
        if globals().get("_EPI") is not None:
            _rd = _EPI.recent_days_context()
            if _rd:
                parts.append(_rd)
    except Exception:
        pass
    return " | ".join(parts)''')

open(p, "w", encoding="utf-8").write(s)
print("patched")
