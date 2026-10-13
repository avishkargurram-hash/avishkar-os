"""The model sometimes writes a tool call as text with the tool name under "action":
{"action":"look_through_camera","parameters":{}}. The recovery scanner only knew
tool/name/function/tool_name. Safe to add: a blob only counts when the value is a
REGISTERED tool name (see _scan_pseudo_tool_json)."""
import sys
p = "/opt/layla/layla_service.py"
s = open(p, encoding="utf-8").read()
old = '_PSEUDO_TOOLCALL_NAME_KEYS = ("tool", "name", "function", "tool_name")\n'
if '"tool_name", "action")' in s:
    print("already patched"); sys.exit(0)
assert s.count(old) == 1, s.count(old)
open(p, "w", encoding="utf-8").write(
    s.replace(old, '_PSEUDO_TOOLCALL_NAME_KEYS = ("tool", "name", "function", "tool_name", "action")\n', 1))
print("patched")
