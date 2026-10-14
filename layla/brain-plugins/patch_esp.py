"""Hook layla_esp into layla_service.py (idempotent). Run in /opt/layla after backup."""
import re, sys
P = "layla_service.py"
s = open(P, encoding="utf-8").read()
if "layla_esp" in s:
    print("already patched"); sys.exit(0)
s, n = re.subn(r'\("layla_identity", "identity"\)\)', '("layla_identity", "identity"),\n                       ("layla_esp", "esp"))', s, count=1)
if n != 1:
    raise SystemExit("tuple anchor not found")
s, n = re.subn(r'^(_cap_init\("layla_identity",[^\n]*\n)', r'\1_cap_init("layla_esp")\n', s, count=1, flags=re.M)
if n != 1:
    raise SystemExit("init anchor not found")
open(P, "w", encoding="utf-8").write(s)
print("patched")
