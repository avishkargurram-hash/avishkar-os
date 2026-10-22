"""Patch layla_service.py to load and wire Browser-Use (Pillar 2) and Open Interpreter Loop (Pillar 8).

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
if "layla_browser" in s and "layla_interpreter" in s:
    print("already patched")
    sys.exit(0)

# 1. Backup before touching
ts = int(time.time())
bak = f"{p}.bak.browser_interpreter.{ts}"
shutil.copy2(p, bak)
print(f"Created timestamped backup: {bak}")

def rep(old, new):
    global s
    assert s.count(old) == 1, f"anchor count {s.count(old)} for {old[:60]!r}"
    s = s.replace(old, new, 1)

# 2. Tool dispatch in execute_tool()
rep(
    '        if globals().get("_HINDSIGHT") is not None and name in _HINDSIGHT.NAMES:\n            return _HINDSIGHT.call(name, args)\n',
    '        if globals().get("_HINDSIGHT") is not None and name in _HINDSIGHT.NAMES:\n            return _HINDSIGHT.call(name, args)\n'
    '        if globals().get("_BROWSER") is not None and name in _BROWSER.NAMES:\n            return _BROWSER.call(name, args)\n'
    '        if globals().get("_INTERPRETER") is not None and name in _INTERPRETER.NAMES:\n            return _INTERPRETER.call(name, args)\n'
)

# 3. Module import and tool registration
rep(
    'except Exception as _e:\n'
    '    _HINDSIGHT = None\n'
    '    print(f"[hindsight] not loaded: {_e}", flush=True)\n',
    'except Exception as _e:\n'
    '    _HINDSIGHT = None\n'
    '    print(f"[hindsight] not loaded: {_e}", flush=True)\n'
    'try:\n'
    '    import layla_browser as _BROWSER\n'
    '    _have = {t["function"]["name"] for t in TOOLS}\n'
    '    TOOLS.extend(t for t in _BROWSER.TOOLS if t["function"]["name"] not in _have)\n'
    '    _TOOL_CATEGORIES["browser"] = set(_BROWSER.NAMES)\n'
    '    _CATEGORY_KEYWORDS["browser"] = tuple(_BROWSER.KEYWORDS)\n'
    '    if "web" in _TOOL_CATEGORIES:\n'
    '        _TOOL_CATEGORIES["web"] |= set(_BROWSER.NAMES)\n'
    '    print(f"[browser] loaded {len(_BROWSER.NAMES)} headless browser-use tools", flush=True)\n'
    'except Exception as _e:\n'
    '    _BROWSER = None\n'
    '    print(f"[browser] not loaded: {_e}", flush=True)\n'
    'try:\n'
    '    import layla_interpreter as _INTERPRETER\n'
    '    _have = {t["function"]["name"] for t in TOOLS}\n'
    '    TOOLS.extend(t for t in _INTERPRETER.TOOLS if t["function"]["name"] not in _have)\n'
    '    _TOOL_CATEGORIES["interpreter"] = set(_INTERPRETER.NAMES)\n'
    '    _CATEGORY_KEYWORDS["interpreter"] = tuple(_INTERPRETER.KEYWORDS)\n'
    '    print(f"[interpreter] loaded {len(_INTERPRETER.NAMES)} self-healing code loop tools", flush=True)\n'
    'except Exception as _e:\n'
    '    _INTERPRETER = None\n'
    '    print(f"[interpreter] not loaded: {_e}", flush=True)\n'
)

# 4. Capability plugins registration
rep(
    'if globals().get("_HINDSIGHT") is not None:\n    _CAP_PLUGINS["layla_hindsight"] = _HINDSIGHT\n',
    'if globals().get("_HINDSIGHT") is not None:\n    _CAP_PLUGINS["layla_hindsight"] = _HINDSIGHT\n'
    'if globals().get("_BROWSER") is not None:\n    _CAP_PLUGINS["layla_browser"] = _BROWSER\n'
    'if globals().get("_INTERPRETER") is not None:\n    _CAP_PLUGINS["layla_interpreter"] = _INTERPRETER\n'
)

# 5. Tool scoping in _select_scoped_tools
rep(
    '        if "hindsight" in _TOOL_CATEGORIES and any(kw in norm for kw in _CATEGORY_KEYWORDS.get("hindsight", ())):\n'
    '            matched_names |= _TOOL_CATEGORIES["hindsight"]\n',
    '        if "hindsight" in _TOOL_CATEGORIES and any(kw in norm for kw in _CATEGORY_KEYWORDS.get("hindsight", ())):\n'
    '            matched_names |= _TOOL_CATEGORIES["hindsight"]\n'
    '        if "browser" in _TOOL_CATEGORIES and any(kw in norm for kw in _CATEGORY_KEYWORDS.get("browser", ())):\n'
    '            matched_names |= _TOOL_CATEGORIES["browser"]\n'
    '        if "interpreter" in _TOOL_CATEGORIES and any(kw in norm for kw in _CATEGORY_KEYWORDS.get("interpreter", ())):\n'
    '            matched_names |= _TOOL_CATEGORIES["interpreter"]\n'
)

# 6. Question tool categories match
rep(
    '_QUESTION_TOOL_CATS = ("world", "worldstate", "hindsight", "visionmem", "affect", "speakers", "l365", "telemetry", "ambient", "social", "almanac", "science")',
    '_QUESTION_TOOL_CATS = ("world", "worldstate", "hindsight", "browser", "interpreter", "visionmem", "affect", "speakers", "l365", "telemetry", "ambient", "social", "almanac", "science")'
)

# 7. Initialization in _cap_init section
rep(
    '_cap_init("layla_hindsight", memory=_memory, push=push_event)\n',
    '_cap_init("layla_hindsight", memory=_memory, push=push_event)\n'
    '_cap_init("layla_browser", memory=_memory, push=push_event)\n'
    '_cap_init("layla_interpreter", memory=_memory, push=push_event)\n'
)

# 8. Compile verification before saving
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

# 9. Atomically write patched code
with open(p, "w", encoding="utf-8") as f:
    f.write(s)

print("SUCCESS: layla_service.py successfully patched for Browser-Use and Open Interpreter!")
