"""Layla didn't know the time or date: answered "3:42 PM EDT" / "Wednesday 12 October" (it was Monday, 21:47 IST).
The current date/time hint was only injected for reminder-ish messages. Inject it on EVERY turn (~30 tokens),
in IST. Anchored on the per-turn reminder assembly; idempotent."""
import sys
p = "/opt/layla/layla_service.py"
s = open(p, encoding="utf-8").read()
if "India time (IST, Asia/Kolkata). Answer any time/date" in s:
    print("already patched"); sys.exit(0)
old = '    if _eil_state["caution"]:\n        _reminder_bits.append(_eil_state["caution"])\n'
assert s.count(old) == 1, s.count(old)
new = ('    try:\n'
       '        _reminder_bits.append("Right now it is " + _dt.datetime.now(IST).strftime("%A %d %B %Y, %I:%M %p")\n'
       '                              + " India time (IST, Asia/Kolkata). Answer any time/date question from this, in IST; "\n'
       '                              "never guess another timezone or date.")\n'
       '    except Exception:\n'
       '        pass\n')
open(p, "w", encoding="utf-8").write(s.replace(old, new + old, 1))
print("patched")
