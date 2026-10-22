import sys
import time
sys.path.insert(0, "/opt/layla")
import layla_service as L
import layla_scientist as S

print("=== 1. Checking Tool Registration in Layla ===")
sci_tools = [t for t in L.TOOLS if t["function"]["name"] in S.NAMES]
print(f"Registered Scientist tools: {[t['function']['name'] for t in sci_tools]}")
assert len(sci_tools) == 4, f"Expected 4 tools, got {len(sci_tools)}"

print("\n=== 2. Testing start_scientific_research (Real Mission Creation) ===")
res_start = L.execute_tool("start_scientific_research", {
    "question": "Can high-pressure lanthanum decahydride maintain superconductivity when doped with nitrogen at lower pressures?",
    "depth": "QUICK"
})
print("Start Result:", res_start)
assert res_start.get("status") == "success", f"Failed: {res_start}"
new_mid = res_start["mission_id"]
print(f"Created Real Mission ID: {new_mid}")

print("\n=== 3. Checking Status of New Mission ===")
res_status = L.execute_tool("get_research_status", {"mission_id": new_mid})
print("New Mission Status Result:", res_status)
assert res_status.get("status") == "success", f"Failed: {res_status}"
assert res_status.get("mission_id") == new_mid

print("\n=== 4. Checking Mission Progress from Workers ===")
# Give workers a few seconds to lease and advance tasks
time.sleep(3)
res_status2 = L.execute_tool("get_research_status", {"mission_id": new_mid})
print("Updated Mission Status:", res_status2.get("output"))

print("\n=== 5. Checking Kill Switch Behavior ===")
import os
os.environ["SCIENTIST"] = "0"
res_kill = L.execute_tool("get_research_status", {"mission_id": new_mid})
print("Kill-switch Result:", res_kill)
assert res_kill.get("status") == "error"
assert "disabled" in res_kill.get("error", "").lower() or "switched off" in res_kill.get("error", "").lower()
os.environ["SCIENTIST"] = "1"
print("Kill switch successfully verified!")

print("\n=== 6. Turn Hint Verification ===")
hint = S.turn_hint(f"What is the status of {new_mid}?")
print("Turn hint result:", hint)
assert hint is not None and new_mid.upper() in hint

print("\n=======================================================")
print("  ALL 6 SCIENTIST OS & LAYLA INTEGRATION TESTS PASSED! ")
print("=======================================================")
