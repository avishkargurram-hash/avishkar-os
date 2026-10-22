import time
import sys
sys.path.insert(0, '/opt/layla')
import layla_service as L

time.sleep(2)

print("=== 1. Testing get_pc_status ===")
res_status = L.execute_tool("get_pc_status", {})
print("PC Status:", res_status)

print("\n=== 2. Direct _exec Testing ===")
res_act = L._exec("pc", "query_pc_activity", {"query": "", "hours": 24})
print("pc_query_activity status:", res_act.get("status"))
print("pc_query_activity output:\n", res_act.get("output"))

res_win = L._exec("pc", "list_windows", {})
print("\npc_list_windows status:", res_win.get("status"))
wins = res_win.get("output", [])
if isinstance(wins, list):
    print(f"Open Windows Count: {len(wins)}")
    for w in wins[:5]:
        print(f" - {w.get('title')}")
else:
    print("Output:", wins)
