"""Patch layla_service.py to load and wire layla_godseye (God's Eye View capability).

Follows standing rules:
- Takes a timestamped backup before touching layla_service.py
- Uses strict anchor assertion (assert s.count(old) == 1)
- Never leaves a broken intermediate file
- Idempotent: exits cleanly if already patched
"""

import os
import shutil
import sys
import time

p = "/opt/layla/layla_service.py"
if not os.path.exists(p):
    # Support running from local repository test directory if needed
    alt_p = "C:/Users/Administrator/Desktop/Nix Meet/Avishkar-OS/layla/Layla Phase0 Work/layla_service.py"
    if os.path.exists(alt_p):
        p = alt_p
    else:
        print(f"Error: {p} not found")
        sys.exit(1)

s = open(p, encoding="utf-8").read()
if "layla_godseye" in s:
    print("already patched")
    sys.exit(0)

# 1. Backup before touching
ts = int(time.time())
bak = f"{p}.bak_{ts}"
shutil.copy2(p, bak)
print(f"Created timestamped backup: {bak}")

def rep(old, new):
    global s
    assert s.count(old) == 1, f"anchor count {s.count(old)} for {old[:60]!r}"
    s = s.replace(old, new, 1)

# 2. Tool dispatch in execute_tool()
rep(
    '        if _VM is not None and name in _VM.NAMES:\n            return _VM.call(name, args)\n',
    '        if _VM is not None and name in _VM.NAMES:\n            return _VM.call(name, args)\n'
    '        if globals().get("_GE") is not None and name in _GE.NAMES:\n            return _GE.call(name, args)\n'
)

# 3. Module import and tool registration
rep(
    '    print(f"[l365] not loaded: {_e}", flush=True)\n',
    '    print(f"[l365] not loaded: {_e}", flush=True)\n'
    'try:\n'
    '    import layla_godseye as _GE\n'
    '    _have = {t["function"]["name"] for t in TOOLS}\n'
    '    TOOLS.extend(t for t in _GE.TOOLS if t["function"]["name"] not in _have)\n'
    '    _TOOL_CATEGORIES["godseye"] = set(_GE.NAMES)\n'
    '    _CATEGORY_KEYWORDS["godseye"] = tuple(_GE.KEYWORDS)\n'
    '    if "world" in _TOOL_CATEGORIES:\n'
    '        _TOOL_CATEGORIES["world"] |= set(_GE.NAMES)\n'
    '    print(f"[godseye] loaded {len(_GE.NAMES)} planetary intelligence tools", flush=True)\n'
    'except Exception as _e:\n'
    '    _GE = None\n'
    '    print(f"[godseye] not loaded: {_e}", flush=True)\n'
)

# 4. Capability plugins registration
rep(
    'if _L365 is not None:\n    _CAP_PLUGINS["layla_l365"] = _L365\n',
    'if _L365 is not None:\n    _CAP_PLUGINS["layla_l365"] = _L365\n'
    'if globals().get("_GE") is not None:\n    _CAP_PLUGINS["layla_godseye"] = _GE\n'
)

# 5. Initialization in _cap_init section
rep(
    '_cap_init("layla_l365", start=True, memory=_memory, execute_tool=lambda n, a: execute_tool(n, a),\n          push=push_event, log_said=_plugin_log_said)\n',
    '_cap_init("layla_l365", start=True, memory=_memory, execute_tool=lambda n, a: execute_tool(n, a),\n          push=push_event, log_said=_plugin_log_said)\n'
    '_cap_init("layla_godseye", memory=_memory, push=push_event)\n'
)

with open(p, "w", encoding="utf-8") as f:
    f.write(s)

print("SUCCESS: layla_service.py successfully patched for God's Eye View!")
