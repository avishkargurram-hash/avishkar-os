import os
import sys
import time

sys.path.insert(0, "/opt/layla")
import layla_service as L
import layla_worldstate as W
import layla_hindsight as H

print("=== 1. Checking Tool Registration in Layla ===")
world_tools = [t for t in L.TOOLS if t["function"]["name"] in W.NAMES]
hindsight_tools = [t for t in L.TOOLS if t["function"]["name"] in H.NAMES]
print(f"Registered WorldState tools ({len(world_tools)}): {[t['function']['name'] for t in world_tools]}")
print(f"Registered Hindsight tools ({len(hindsight_tools)}): {[t['function']['name'] for t in hindsight_tools]}")
assert len(world_tools) == 3, f"Expected 3 WorldState tools, got {len(world_tools)}"
assert len(hindsight_tools) == 2, f"Expected 2 Hindsight tools, got {len(hindsight_tools)}"

print("\n=== 2. Testing get_world_state (Live Digital Reality Graph) ===")
res_world = L.execute_tool("get_world_state", {"focus": "all"})
print("WorldState Output:", res_world.get("output"))
assert res_world.get("status") == "success", f"Failed: {res_world}"
assert len(res_world.get("servers", [])) >= 3, f"Expected >=3 servers, got {len(res_world.get('servers', []))}"
assert len(res_world.get("devices", [])) >= 3, f"Expected >=3 devices, got {len(res_world.get('devices', []))}"

print("\n=== 3. Testing get_hindsight_lessons (Experiential Reflection) ===")
res_ref = L.execute_tool("get_hindsight_lessons", {"domain": "all"})
print("Hindsight Lessons Output:", res_ref.get("output"))
assert res_ref.get("status") == "success", f"Failed: {res_ref}"
assert res_ref.get("count", 0) >= 3, f"Expected >=3 lessons, got {res_ref.get('count')}"

print("\n=== 4. Testing record_learned_lesson ===")
res_record = L.execute_tool("record_learned_lesson", {
    "domain": "system",
    "pattern": "oracle latency",
    "intent": "Maintain sub-2s conversational latency",
    "trigger_condition": "Heavy jobs executed on executive brain node",
    "lesson": "Always delegate heavy database queries and compute to tv-mum-01 or Windows PC to preserve low latency on Oracle brain."
})
print("Record Lesson Result:", res_record)
assert res_record.get("status") == "success", f"Failed: {res_record}"

print("\n=== 5. Testing Turn Hints ===")
hint_world = W.turn_hint("What is the status of our servers and infrastructure?")
print("WorldState Turn Hint:", hint_world)
assert hint_world is not None and "Digital Reality Graph" in hint_world

hint_hind = H.turn_hint("What is the fan speed for bedroom fan?")
print("Hindsight Turn Hint:", hint_hind)
assert hint_hind is not None and "Hindsight Operational Guidance" in hint_hind

print("\n=== 6. Testing Kill Switches ===")
os.environ["WORLDSTATE"] = "0"
os.environ["HINDSIGHT"] = "0"

res_w_kill = L.execute_tool("get_world_state", {})
res_h_kill = L.execute_tool("get_hindsight_lessons", {})
print("WorldState Kill-switch:", res_w_kill)
print("Hindsight Kill-switch:", res_h_kill)
assert res_w_kill.get("status") == "error"
assert res_h_kill.get("status") == "error"

os.environ["WORLDSTATE"] = "1"
os.environ["HINDSIGHT"] = "1"
print("Kill switches verified successfully!")

print("\n=== 7. Testing Asynchronous Tool Outcome Telemetry ===")
H.log_tool_outcome("test_tool", "SUCCESS", latency_ms=12.5)
time.sleep(1.0)
print("Async outcome telemetry dispatched without error!")

print("\n=======================================================")
print("  ALL 7 WORLDSTATE & HINDSIGHT INTEGRATION TESTS PASSED! ")
print("=======================================================")
