"""Patch layla_service.py to load and wire layla_scientist (Scientist OS capability).

Follows standing rules:
- Takes a timestamped backup before touching layla_service.py
- Uses strict anchor assertion (assert s.count(old) == 1)
- Never leaves a broken intermediate file
- Compiles via py_compile before writing
- Idempotent: exits cleanly if already patched
"""

import os
import py_compile
import shutil
import sys
import tempfile
import time

p = "/opt/layla/layla_service.py"
if not os.path.exists(p):
    alt_p = "C:/Users/Administrator/Desktop/Nix Meet/Avishkar-OS/layla/Layla Phase0 Work/layla_service.py"
    if os.path.exists(alt_p):
        p = alt_p
    else:
        print(f"Error: {p} not found")
        sys.exit(1)

s = open(p, encoding="utf-8").read()
if "layla_scientist" in s:
    print("already patched")
    sys.exit(0)

# 1. Backup before touching
ts = int(time.time())
bak = f"{p}.bak.scientist.{ts}"
shutil.copy2(p, bak)
print(f"Created timestamped backup: {bak}")

def rep(old, new):
    global s
    assert s.count(old) == 1, f"anchor count {s.count(old)} for {old[:60]!r}"
    s = s.replace(old, new, 1)

# 2. Tool dispatch in execute_tool()
rep(
    '        if globals().get("_GE") is not None and name in _GE.NAMES:\n            return _GE.call(name, args)\n',
    '        if globals().get("_GE") is not None and name in _GE.NAMES:\n            return _GE.call(name, args)\n'
    '        if globals().get("_SCI") is not None and name in _SCI.NAMES:\n            return _SCI.call(name, args)\n'
)

# 3. Module import and tool registration
rep(
    '    _GE = None\n    print(f"[godseye] not loaded: {_e}", flush=True)\n',
    '    _GE = None\n    print(f"[godseye] not loaded: {_e}", flush=True)\n'
    'try:\n'
    '    import layla_scientist as _SCI\n'
    '    _have = {t["function"]["name"] for t in TOOLS}\n'
    '    TOOLS.extend(t for t in _SCI.TOOLS if t["function"]["name"] not in _have)\n'
    '    _TOOL_CATEGORIES["science"] = set(_SCI.NAMES)\n'
    '    _CATEGORY_KEYWORDS["science"] = tuple(_SCI.KEYWORDS)\n'
    '    if "research" in _TOOL_CATEGORIES:\n'
    '        _TOOL_CATEGORIES["research"] |= set(_SCI.NAMES)\n'
    '    print(f"[scientist] loaded {len(_SCI.NAMES)} scientific research tools", flush=True)\n'
    'except Exception as _e:\n'
    '    _SCI = None\n'
    '    print(f"[scientist] not loaded: {_e}", flush=True)\n'
)

# 4. Capability plugins registration
rep(
    'if globals().get("_GE") is not None:\n    _CAP_PLUGINS["layla_godseye"] = _GE\n',
    'if globals().get("_GE") is not None:\n    _CAP_PLUGINS["layla_godseye"] = _GE\n'
    'if globals().get("_SCI") is not None:\n    _CAP_PLUGINS["layla_scientist"] = _SCI\n'
)

# 5. Initialization in _cap_init section
rep(
    '_cap_init("layla_godseye", memory=_memory, push=push_event)\n',
    '_cap_init("layla_godseye", memory=_memory, push=push_event)\n'
    '_cap_init("layla_scientist", memory=_memory, push=push_event)\n'
)

# 6. Tool scoping in _select_scoped_tools
rep(
    '        if _RESEARCH_TRIGGER_RE.search(norm):\n            matched_names |= _TOOL_CATEGORIES["web"]\n',
    '        if _RESEARCH_TRIGGER_RE.search(norm):\n            matched_names |= _TOOL_CATEGORIES["web"]\n'
    '        if "science" in _TOOL_CATEGORIES and any(kw in norm for kw in _CATEGORY_KEYWORDS.get("science", ())):\n'
    '            matched_names |= _TOOL_CATEGORIES["science"]\n'
)

# 7. Compile verification before saving
with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".py", delete=False) as tf:
    tf.write(s)
    tname = tf.name

try:
    py_compile.compile(tname, doraise=True)
    print("py_compile verification passed successfully.")
except Exception as exc:
    os.remove(tname)
    print(f"FATAL: py_compile failed: {exc}. Aborting patch.")
    sys.exit(1)

os.remove(tname)

# 8. Atomically write patched code
with open(p, "w", encoding="utf-8") as f:
    f.write(s)

print("SUCCESS: layla_service.py successfully patched for Scientist OS!")
