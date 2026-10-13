"""Wire conversation mode (layla_companion) + the Almanac bridge into layla_service.py.
 - both registered in the _CAP_PLUGINS loop (bridge tools + 'almanac' scope keywords)
 - 'almanac' added to the question-tool gate (so "what's on my almanac today?" gets tools)
 - /ask: "conversation mode on/off" answered instantly (no LLM), stored in history, mode_change returned;
   every /ask reply carries mode = companion|normal for the page.
Usage: python patch_convmode.py [path]. Idempotent; anchors asserted."""
import sys
p = sys.argv[1] if len(sys.argv) > 1 else "/opt/layla/layla_service.py"
s = open(p, encoding="utf-8").read()
if "layla_companion" in s:
    print("already patched"); sys.exit(0)


def rep(old, new):
    global s
    assert s.count(old) == 1, f"anchor count {s.count(old)}: {old[:80]!r}"
    s = s.replace(old, new, 1)


rep('                       ("layla_social", "social")):\n',
    '                       ("layla_social", "social"), ("layla_companion", None),\n'
    '                       ("layla_almanac_bridge", "almanac")):\n')
rep('_cap_init("layla_social", start=True,',
    '_cap_init("layla_companion", memory=_memory)\n_cap_init("layla_almanac_bridge")\n_cap_init("layla_social", start=True,')
rep('_QUESTION_TOOL_CATS = ("world", "visionmem", "affect", "speakers", "l365", "telemetry", "ambient", "social")',
    '_QUESTION_TOOL_CATS = ("world", "visionmem", "affect", "speakers", "l365", "telemetry", "ambient", "social", "almanac")')
rep('''                result = ask(m)
                try:
                    if isinstance(result, dict) and isinstance(result.get("answer"), str):
''',
'''                _cmp = _CAP_PLUGINS.get("layla_companion")
                try:
                    _cmd = _cmp.command(m) if _cmp is not None else None
                except Exception:
                    _cmd = None
                if _cmd:
                    _reply, _chg = _cmd
                    try:
                        _h = _memory.recall("episodic", CONV_KEY) or []
                        _h += [{"role": "user", "content": m}, {"role": "assistant", "content": _reply}]
                        _memory.remember("episodic", CONV_KEY, _h[-40:])
                        _archive_turn("user", m)
                        _archive_turn("assistant", _reply)
                    except Exception:
                        pass
                    print(f"[companion] conversation mode {_chg}", flush=True)
                    return self._json(200, {"answer": _reply, "tone": "excited" if _chg == "on" else "warm",
                                            "actions": [], "mode_change": _chg,
                                            "mode": "companion" if _chg == "on" else "normal"})
                result = ask(m)
                try:
                    if isinstance(result, dict):
                        result["mode"] = "companion" if (_cmp is not None and _cmp.is_on()) else "normal"
                except Exception:
                    pass
                try:
                    if isinstance(result, dict) and isinstance(result.get("answer"), str):
''')
open(p, "w", encoding="utf-8").write(s)
print("convmode patched")
