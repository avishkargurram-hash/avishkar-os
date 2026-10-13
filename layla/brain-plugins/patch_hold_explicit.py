"""Hold mode -> explicit cues only (owner decision 2026-10-12, "option B").
Keeps: "ok now listen" / "now listen" / "listen" (alone) / "let me tell you something" and its close variants,
       + end phrases "that's it" / "go ahead".
Removes: the dangling-word guess (and/so/that/um/comma...), the generic cues (hold on, wait, also, ok so...),
         the Telugu/Tenglish cues and "అంతే" as an end phrase.
Usage: python patch_hold_explicit.py [path]. Idempotent, anchored."""
import re, sys
p = sys.argv[1] if len(sys.argv) > 1 else "/opt/layla/web/face/index.html"
s = open(p, encoding="utf-8").read()
if "HOLD_EXPLICIT_ONLY" in s:
    print("already patched"); sys.exit(0)


def must_once(pat, flags=0):
    assert len(re.findall(pat, s, flags)) == 1, f"anchor count != 1: {pat[:70]!r}"


# 1. end phrases: English only
old_end = "(?:that'?s it|that is it|go ahead|అంతే)[\\s.!?]*$/i;"
assert s.count(old_end) == 1, s.count(old_end)
s = s.replace(old_end, "(?:that'?s it|that is it|go ahead)[\\s.!?]*$/i;", 1)

# 2. announcer cues: the explicit ones only
must_once(r"^  const HOLD_CUE_RE = /.*$", re.M)
_NEW_CUE = ("  const HOLD_CUE_RE = /(?:^|[\\s,.])(?:ok(?:ay)? now listen|now listen|let me tell you something|"
            "i (?:want|need) to tell you something|i have something to tell you)[\\s,.!?]*$/i;  // HOLD_EXPLICIT_ONLY")
s = re.sub(r"^  const HOLD_CUE_RE = /.*$", lambda m: _NEW_CUE, s, count=1, flags=re.M)

# 3. no dangling-word guessing: remove the helper sets and make holdCue announcer-only
s = re.sub(r"^  const HOLD_TRAIL = .*\n", "", s, count=1, flags=re.M)
s = re.sub(r"^  // words that also END normal sentences.*\n", "", s, count=1, flags=re.M)
s = re.sub(r"^  const HOLD_SOFT = .*\n", "", s, count=1, flags=re.M)
i = s.index("  function holdCue(t){")
j = s.index("  let holdBuf=", i)
s = s[:i] + ("  function holdCue(t){\n"
             "    const s=(t||'').trim(); if(!s) return '';\n"
             "    if(/^listen[\\s.!?]*$/i.test(s)) return 'announce';\n"
             "    return HOLD_CUE_RE.test(s) ? 'announce' : '';\n"
             "  }\n") + s[j:]
for dead in ("HOLD_TRAIL", "HOLD_SOFT"):
    assert dead not in s, dead
open(p, "w", encoding="utf-8").write(s)
print("hold mode: explicit cues only")
