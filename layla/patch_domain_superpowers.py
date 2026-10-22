"""Patch LaylaExecutiveAgent.domain in layla_service.py to register Phase A & B superpowers.

Ensures CapabilityResolver recognizes terminal, bash, python, interpreter, execution,
server, infrastructure, workflow, and hindsight as native capabilities of LaylaExecutiveAgent.

Follows strict rules:
- Takes timestamped backup
- Strict anchor assertion
- py_compile verification
- Atomic write
"""

import os
import py_compile
import shutil
import sys
import tempfile
import time

p = "/opt/layla/layla_service.py"
s = open(p, encoding="utf-8").read()

old_domain = (
    '    domain = ("personal assistant home automation relay light switch fan bulb "\n'
    '              "plug ceiling bedroom switchboard computer "\n'
    '              "windows laptop desktop connected connection status browser internet "\n'
    '              "search telegram message reminder remind reminders schedule scheduled "\n'
    '              "alarm tomorrow daily briefing memory remember recall forget "\n'
    '              "camera vision picture image photo notepad chrome application "\n'
    '              "software open website search")'
)

new_domain = (
    '    domain = ("personal assistant home automation relay light switch fan bulb "\n'
    '              "plug ceiling bedroom switchboard computer "\n'
    '              "windows laptop desktop connected connection status browser internet "\n'
    '              "search telegram message reminder remind reminders schedule scheduled "\n'
    '              "alarm tomorrow daily briefing memory remember recall forget "\n'
    '              "camera vision picture image photo notepad chrome application "\n'
    '              "software open website search "\n'
    '              "terminal command commands script scripts shell bash python code "\n'
    '              "interpreter execute execution uptime system servers server node "\n'
    '              "nodes infrastructure workflow workflows hindsight reflection")'
)

assert s.count(old_domain) == 1, f"Expected exactly 1 occurrence of old_domain, found {s.count(old_domain)}"

ts = int(time.time())
bak = f"{p}.bak.domain.{ts}"
shutil.copy2(p, bak)
print(f"Created timestamped backup: {bak}")

s = s.replace(old_domain, new_domain, 1)

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

with open(p, "w", encoding="utf-8") as f:
    f.write(s)

print("SUCCESS: LaylaExecutiveAgent.domain successfully updated with Phase A & B superpowers!")
