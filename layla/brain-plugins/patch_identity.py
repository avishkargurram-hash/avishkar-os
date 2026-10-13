"""Task 4a: hook layla_identity into layla_service.py (idempotent). Run in /opt/layla after backup."""
import re
import sys

P = "layla_service.py"
s = open(P, encoding="utf-8").read()
if "layla_identity" in s:
    print("already patched"); sys.exit(0)


def sub1(pat, repl, flags=0):
    global s
    s, n = re.subn(pat, repl, s, count=1, flags=flags)
    if n != 1:
        raise SystemExit("anchor not found: " + pat[:60])


# 1. single-face recogniser outcomes
sub1(r'^(\s+)(return f"Unrecognized face --)', r'\1_ident_note("face", [], 1)\n\1\2', re.M)
sub1(r'^(\s+)(return \(f"I can see a face but I\'m not confident)', r'\1_ident_note("face", [], 1)\n\1\2', re.M)
sub1(r'^(\s+)(return f"Recognized: \{best_name\} \(similarity)', r'\1_ident_note("face", [best_name], 0)\n\1\2', re.M)

# 2. room / door scan result (named + unrecognised faces)
sub1(r'^(\s+)(print\(f"\[\{\'DOOR\' if source == \'door\' else \'ROOM\'\} SCAN\] \{w\}x\{h\})',
     r'\1try:\n\1    _ident_note("face", [p["name"] for p in scene["people"] if p["name"]], '
     r'sum(1 for p in scene["people"] if not p["name"]))\n\1except Exception:\n\1    pass\n\1\2', re.M)

# 3. register the plugin + helper + init
sub1(r'\("layla_almanac_bridge", "almanac"\)\)', '("layla_almanac_bridge", "almanac"),\n                       ("layla_identity", "identity"))')
sub1(r'^_cap_init\("layla_approvals", push=push_event\)',
     'def _ident_note(src, names=(), unknown=0):\n'
     '    _im = _CAP_PLUGINS.get("layla_identity")\n'
     '    if _im is not None:\n'
     '        _im.note(src, names, unknown)\n\n'
     '_cap_init("layla_identity", memory=_memory, speakers=_CAP_PLUGINS.get("layla_speakers"), owner=OWNER_NAME)\n'
     '_cap_init("layla_approvals", push=push_event)', re.M)
open(P, "w", encoding="utf-8").write(s)
print("patched")
