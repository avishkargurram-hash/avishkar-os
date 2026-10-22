import sys
p = "/opt/layla/layla_service.py"
s = open(p, encoding="utf-8").read()
if "_L365.team_line()" in s:
    print("already patched"); sys.exit(0)
old = '    _CATEGORY_KEYWORDS["l365"] = tuple(_L365.KEYWORDS)\n'
assert s.count(old) == 1, s.count(old)
s = s.replace(old, old + '    _team = _L365.team_line()\n    SYSTEM += _team\n    SYSTEM_CONVERSATIONAL += _team\n', 1)
open(p, "w", encoding="utf-8").write(s)
print("patched")
