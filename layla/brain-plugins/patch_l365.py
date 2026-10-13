"""Wires layla_l365 (agent gateway + Layla-as-boss tools + morning briefing) into
layla_service.py. Anchored, idempotent, fails loudly. Run AFTER patch_caps_3_11."""
import sys
p = "/opt/layla/layla_service.py"
s = open(p, encoding="utf-8").read()
if "layla_l365" in s:
    print("already patched"); sys.exit(0)

def rep(old, new):
    global s
    assert s.count(old) == 1, f"anchor count {s.count(old)} for {old[:70]!r}"
    s = s.replace(old, new, 1)

# 1. register her boss tools + scope (reuses the _CAP_PLUGINS registry/dispatch from patch_caps_3_11)
rep('# Task 1 capability plugins (#3 affect',
    'try:\n'
    '    import layla_l365 as _L365\n'
    '    _have = {t["function"]["name"] for t in TOOLS}\n'
    '    TOOLS.extend(t for t in _L365.TOOLS if t["function"]["name"] not in _have)\n'
    '    _TOOL_CATEGORIES["l365"] = set(_L365.NAMES)\n'
    '    _CATEGORY_KEYWORDS["l365"] = tuple(_L365.KEYWORDS)\n'
    'except Exception as _e:\n'
    '    _L365 = None\n'
    '    print(f"[l365] not loaded: {_e}", flush=True)\n'
    '# Task 1 capability plugins (#3 affect')
rep('_CAP_PLUGINS = {}\n', '_CAP_PLUGINS = {}\nif _L365 is not None:\n    _CAP_PLUGINS["layla_l365"] = _L365\n')

# 2. init + start (needs execute_tool + push + memory, all defined by now)
rep('_cap_init("layla_social", start=True,',
    '_cap_init("layla_l365", start=True, memory=_memory, execute_tool=lambda n, a: execute_tool(n, a),\n'
    '          push=push_event, log_said=_plugin_log_said)\n'
    '_cap_init("layla_social", start=True,')

# 3. POST /agent/gateway (own auth: IP + per-agent token; deliberately NOT owner-cookie)
rep('        if path == "/telemetry/ingest":\n',
    '        if path == "/agent/gateway":\n'
    '            if _L365 is None:\n'
    '                return self._json(404, {"error": "not found"})\n'
    '            return _L365.handle(self, data)\n'
    '        if path == "/telemetry/ingest":\n')

open(p, "w", encoding="utf-8").write(s)
print("patched")
