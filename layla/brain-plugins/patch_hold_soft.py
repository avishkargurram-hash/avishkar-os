"""Hold mode false-holds: "It's good actually." / "I don't think so." / "Can you do that?" ended in a
'connector' word but are complete sentences. Soft words only hold when there is NO terminal punctuation.
Usage: python patch_hold_soft.py [path]. Idempotent, anchored."""
import sys
p = sys.argv[1] if len(sys.argv) > 1 else "/opt/layla/web/face/index.html"
s = open(p, encoding="utf-8").read()
if "HOLD_SOFT" in s:
    print("already patched"); sys.exit(0)
old = "    if(HOLD_TRAIL.has(w[w.length-1])) return 'connector';\n"
assert s.count(old) == 1, s.count(old)
new = ("    const lastW=w[w.length-1], terminal=/[.!?।]\\s*$/.test(s);\n"
       "    if(HOLD_TRAIL.has(lastW) && !(terminal && HOLD_SOFT.has(lastW))) return 'connector';\n")
s = s.replace(old, new, 1)
old2 = "  const HOLD_TRAIL = new Set("
assert s.count(old2) == 1
s = s.replace(old2, "  // words that also END normal sentences: only a connector when the sentence has no final punctuation\n"
                    "  const HOLD_SOFT = new Set(['that','so','like','actually','basically','then','which','too']);\n" + old2, 1)
open(p, "w", encoding="utf-8").write(s)
print("hold soft-word patch applied")
