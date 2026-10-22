import os
import sys
import time

sys.path.insert(0, "/opt/layla")
import layla_service as L
import layla_browser as B
import layla_interpreter as I

print("=== 1. Checking Tool Registration in Layla ===")
browser_tools = [t for t in L.TOOLS if t["function"]["name"] in B.NAMES]
interpreter_tools = [t for t in L.TOOLS if t["function"]["name"] in I.NAMES]
print(f"Registered Browser tools ({len(browser_tools)}): {[t['function']['name'] for t in browser_tools]}")
print(f"Registered Interpreter tools ({len(interpreter_tools)}): {[t['function']['name'] for t in interpreter_tools]}")
assert len(browser_tools) == 3, f"Expected 3 Browser tools, got {len(browser_tools)}"
assert len(interpreter_tools) == 2, f"Expected 2 Interpreter tools, got {len(interpreter_tools)}"

print("\n=== 2. Testing search_web (Headless Bing Scraping via tv-mum-01) ===")
res_search = L.execute_tool("search_web", {"query": "deep learning transformer advances 2026", "max_results": 3})
print("Search Status:", res_search.get("status"))
print("Search Count:", res_search.get("count"))
print("Search Output Preview:\n", res_search.get("output")[:200])
assert res_search.get("status") == "success", f"Failed: {res_search}"
assert res_search.get("count", 0) > 0, "Expected at least 1 search result"

print("\n=== 3. Testing browse_web (Headless Chromium DOM Rendering via tv-mum-01) ===")
res_browse = L.execute_tool("browse_web", {"url": "https://example.com"})
print("Browse Status:", res_browse.get("status"))
print("Browse Title:", res_browse.get("title"))
print("Browse Latency:", res_browse.get("latency_ms"), "ms")
assert res_browse.get("status") == "success", f"Failed: {res_browse}"
assert "Example Domain" in res_browse.get("title", "")

print("\n=== 4. Testing run_terminal_command (Standard Bash via tv-mum-01) ===")
res_cmd = L.execute_tool("run_terminal_command", {"command": "uname -a && uptime"})
print("Command Status:", res_cmd.get("status"))
print("Command Attempts:", res_cmd.get("attempts"))
print("Command Output:\n", res_cmd.get("output"))
assert res_cmd.get("status") == "success", f"Failed: {res_cmd}"
assert "Linux" in res_cmd.get("output", "")

print("\n=== 5. Testing run_self_healing_script (Autonomous Repair via tv-mum-01) ===")
# Clean any previous directory
L.execute_tool("run_terminal_command", {"command": "rm -rf /tmp/sci_phase_b_test_e2e"})
script = """
import os
path = '/tmp/sci_phase_b_test_e2e/nested/test.txt'
with open(path, 'w') as f:
    f.write('self-healing verified')
print('HEALED_AND_WRITTEN')
"""
res_heal = L.execute_tool("run_self_healing_script", {"code": script, "language": "python"})
print("Self-Healing Status:", res_heal.get("status"))
print("Self-Healing Attempts:", res_heal.get("attempts"))
print("Self-Healing Output:\n", res_heal.get("output"))
assert res_heal.get("status") == "success", f"Failed: {res_heal}"
assert res_heal.get("attempts") == 2, f"Expected 2 attempts (1 failure + 1 repair), got {res_heal.get('attempts')}"
assert "HEALED_AND_WRITTEN" in res_heal.get("output", "")

print("\n=== 6. Testing Tool Scoping & Category Keywords ===")
scoped_b = L._select_scoped_tools("Can you browse example.com and check the contents?")
scoped_names_b = {t["function"]["name"] for t in scoped_b}
print("Scoped tools for browse request:", scoped_names_b & set(B.NAMES))
assert "browse_web" in scoped_names_b, "browse_web should be included in scoped tools"

scoped_i = L._select_scoped_tools("Please run bash command to check system disk space")
scoped_names_i = {t["function"]["name"] for t in scoped_i}
print("Scoped tools for terminal request:", scoped_names_i & set(I.NAMES))
assert "run_terminal_command" in scoped_names_i, "run_terminal_command should be included in scoped tools"

print("\n=== 7. Testing Turn Hints ===")
hint_b = B.turn_hint("Can you search web for the latest research?")
print("Browser Turn Hint:", hint_b)
assert hint_b is not None and "browse_web" in hint_b

hint_i = I.turn_hint("Run command in terminal to check memory")
print("Interpreter Turn Hint:", hint_i)
assert hint_i is not None and "run_terminal_command" in hint_i

print("\n=== 8. Testing Kill Switches ===")
os.environ["BROWSER_USE"] = "0"
os.environ["OPEN_INTERPRETER"] = "0"

res_b_kill = L.execute_tool("browse_web", {"url": "https://example.com"})
res_i_kill = L.execute_tool("run_terminal_command", {"command": "ls"})
print("Browser Kill-switch:", res_b_kill)
print("Interpreter Kill-switch:", res_i_kill)
assert res_b_kill.get("status") == "error"
assert res_i_kill.get("status") == "error"

os.environ["BROWSER_USE"] = "1"
os.environ["OPEN_INTERPRETER"] = "1"
print("Kill switches verified successfully!")

print("\n=======================================================")
print("  ALL 8 BROWSER & INTERPRETER INTEGRATION TESTS PASSED! ")
print("=======================================================")
