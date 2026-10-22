"""Patch layla_service.py to load and wire WorldState (Pillar 7) and Hindsight (Pillar 1).

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
if "layla_worldstate" in s and "layla_hindsight" in s:
    print("already patched")
    sys.exit(0)

# 1. Backup before touching
ts = int(time.time())
bak = f"{p}.bak.world_hindsight.{ts}"
shutil.copy2(p, bak)
print(f"Created timestamped backup: {bak}")

def rep(old, new):
    global s
    assert s.count(old) == 1, f"anchor count {s.count(old)} for {old[:60]!r}"
    s = s.replace(old, new, 1)

# 2. Tool dispatch in execute_tool()
rep(
    '        if globals().get("_SCI") is not None and name in _SCI.NAMES:\n            return _SCI.call(name, args)\n',
    '        if globals().get("_SCI") is not None and name in _SCI.NAMES:\n            return _SCI.call(name, args)\n'
    '        if globals().get("_WORLD") is not None and name in _WORLD.NAMES:\n            return _WORLD.call(name, args)\n'
    '        if globals().get("_HINDSIGHT") is not None and name in _HINDSIGHT.NAMES:\n            return _HINDSIGHT.call(name, args)\n'
)

# 3. Module import and tool registration
rep(
    'except Exception as _e:\n'
    '    _SCI = None\n'
    '    print(f"[scientist] not loaded: {_e}", flush=True)\n',
    'except Exception as _e:\n'
    '    _SCI = None\n'
    '    print(f"[scientist] not loaded: {_e}", flush=True)\n'
    'try:\n'
    '    import layla_worldstate as _WORLD\n'
    '    _have = {t["function"]["name"] for t in TOOLS}\n'
    '    TOOLS.extend(t for t in _WORLD.TOOLS if t["function"]["name"] not in _have)\n'
    '    _TOOL_CATEGORIES["worldstate"] = set(_WORLD.NAMES)\n'
    '    _CATEGORY_KEYWORDS["worldstate"] = tuple(_WORLD.KEYWORDS)\n'
    '    if "world" in _TOOL_CATEGORIES:\n'
    '        _TOOL_CATEGORIES["world"] |= set(_WORLD.NAMES)\n'
    '    print(f"[worldstate] loaded {len(_WORLD.NAMES)} digital reality graph tools", flush=True)\n'
    'except Exception as _e:\n'
    '    _WORLD = None\n'
    '    print(f"[worldstate] not loaded: {_e}", flush=True)\n'
    'try:\n'
    '    import layla_hindsight as _HINDSIGHT\n'
    '    _have = {t["function"]["name"] for t in TOOLS}\n'
    '    TOOLS.extend(t for t in _HINDSIGHT.TOOLS if t["function"]["name"] not in _have)\n'
    '    _TOOL_CATEGORIES["hindsight"] = set(_HINDSIGHT.NAMES)\n'
    '    _CATEGORY_KEYWORDS["hindsight"] = tuple(_HINDSIGHT.KEYWORDS)\n'
    '    print(f"[hindsight] loaded {len(_HINDSIGHT.NAMES)} experiential reflection tools", flush=True)\n'
    'except Exception as _e:\n'
    '    _HINDSIGHT = None\n'
    '    print(f"[hindsight] not loaded: {_e}", flush=True)\n'
)

# 4. Capability plugins registration
rep(
    'if globals().get("_SCI") is not None:\n    _CAP_PLUGINS["layla_scientist"] = _SCI\n',
    'if globals().get("_SCI") is not None:\n    _CAP_PLUGINS["layla_scientist"] = _SCI\n'
    'if globals().get("_WORLD") is not None:\n    _CAP_PLUGINS["layla_worldstate"] = _WORLD\n'
    'if globals().get("_HINDSIGHT") is not None:\n    _CAP_PLUGINS["layla_hindsight"] = _HINDSIGHT\n'
)

# 5. Tool scoping in _select_scoped_tools
rep(
    '        if "science" in _TOOL_CATEGORIES and any(kw in norm for kw in _CATEGORY_KEYWORDS.get("science", ())):\n'
    '            matched_names |= _TOOL_CATEGORIES["science"]\n',
    '        if "science" in _TOOL_CATEGORIES and any(kw in norm for kw in _CATEGORY_KEYWORDS.get("science", ())):\n'
    '            matched_names |= _TOOL_CATEGORIES["science"]\n'
    '        if "worldstate" in _TOOL_CATEGORIES and any(kw in norm for kw in _CATEGORY_KEYWORDS.get("worldstate", ())):\n'
    '            matched_names |= _TOOL_CATEGORIES["worldstate"]\n'
    '        if "hindsight" in _TOOL_CATEGORIES and any(kw in norm for kw in _CATEGORY_KEYWORDS.get("hindsight", ())):\n'
    '            matched_names |= _TOOL_CATEGORIES["hindsight"]\n'
)

# 6. Question tool categories match
rep(
    '_QUESTION_TOOL_CATS = ("world", "visionmem", "affect", "speakers", "l365", "telemetry", "ambient", "social", "almanac", "science")',
    '_QUESTION_TOOL_CATS = ("world", "worldstate", "hindsight", "visionmem", "affect", "speakers", "l365", "telemetry", "ambient", "social", "almanac", "science")'
)

# 7. Asynchronous tool telemetry hook in agent execution loop
rep(
    '                tool_records.append({"tool_name": fname, "input": fargs, "output": result.get("output"),\n'
    '                                      "error": result.get("error")})\n',
    '                tool_records.append({"tool_name": fname, "input": fargs, "output": result.get("output"),\n'
    '                                      "error": result.get("error")})\n'
    '                try:\n'
    '                    if globals().get("_HINDSIGHT") is not None:\n'
    '                        _HINDSIGHT.log_tool_outcome(fname, result.get("status", "SUCCESS"), result.get("error"), input_params=fargs)\n'
    '                except Exception:\n'
    '                    pass\n'
)

# 8. Initialization in _cap_init section
rep(
    '_cap_init("layla_scientist", memory=_memory, push=push_event)\n',
    '_cap_init("layla_scientist", memory=_memory, push=push_event)\n'
    '_cap_init("layla_worldstate", memory=_memory, push=push_event)\n'
    '_cap_init("layla_hindsight", memory=_memory, push=push_event)\n'
)

# 9. Compile verification before saving
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

# 10. Atomically write patched code
with open(p, "w", encoding="utf-8") as f:
    f.write(s)

print("SUCCESS: layla_service.py successfully patched for WorldState and Hindsight!")
