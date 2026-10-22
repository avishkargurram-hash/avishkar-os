import sys
sys.path.insert(0, "/opt/layla")
import layla_service as L

msg = "What is the status of our servers and active infrastructure?"
tools = L._select_scoped_tools(msg)
names = [t["function"]["name"] for t in tools]
print("Scoped tools count:", len(names))
print("Is get_world_state present?", "get_world_state" in names)
print("Is get_hindsight_lessons present?", "get_hindsight_lessons" in names)
print("Matched categories:", [c for c, p in L._CATEGORY_PATTERNS.items() if p.search(msg.lower())])
