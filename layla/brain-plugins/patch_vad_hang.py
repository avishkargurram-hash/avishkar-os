"""Set the mic VAD silence hang (end-of-utterance cut) in web/face/index.html.
Usage: python patch_vad_hang.py <ms> [path]. One anchored number; idempotent per value."""
import re, sys
ms = int(sys.argv[1])
p = sys.argv[2] if len(sys.argv) > 2 else "/opt/layla/web/face/index.html"
s = open(p, encoding="utf-8").read()
pat = r"(const VAD_CFG = \{ MIN_THR:0\.015, NOISE_MULT:3, HANG_MS:)(\d+)(,)"
assert len(re.findall(pat, s)) == 1, "VAD_CFG anchor not found exactly once"
cur = int(re.search(pat, s).group(2))
if cur == ms:
    print("already", ms); sys.exit(0)
s = re.sub(pat, lambda m: m.group(1) + str(ms) + m.group(3), s, count=1)
open(p, "w", encoding="utf-8").write(s)
print("HANG_MS %d -> %d" % (cur, ms))
