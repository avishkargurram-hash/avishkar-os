"""Small fix: "look at me" / "how do I look" / "what am I holding" now force the camera look,
like "can you see me" already did. Deliberately NOT "look at this" (too often about text/links)."""
import sys
p = "/opt/layla/layla_service.py"
s = open(p, encoding="utf-8").read()
if "look at me|have a look at me" in s:
    print("already patched"); sys.exit(0)
old = '    r"what else can you see|what else do you see|look around|"\n'
assert s.count(old) == 1, s.count(old)
new = (old +
       '    r"look at me|have a look at me|take a look at me|how do i look|"\n'
       '    r"what am i (?:holding|wearing)|what is in my hand|"\n')
open(p, "w", encoding="utf-8").write(s.replace(old, new, 1))
print("patched")
