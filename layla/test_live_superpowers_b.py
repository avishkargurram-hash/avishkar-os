import json
import time
import urllib.request
import sys

sys.path.insert(0, "/opt/layla")
import layla_service as L

token = L._sign_session(L.OWNER_EMAIL, time.time() + 3600)

def ask(msg):
    url = "http://127.0.0.1:8100/ask"
    payload = json.dumps({"message": msg}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    req = urllib.request.Request(url, data=payload, headers=headers)
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=45) as resp:
        elapsed = time.perf_counter() - t0
        data = json.loads(resp.read().decode("utf-8"))
        return data, elapsed

print("=== Query 1: Can you browse example.com and summarize what is on the page? ===")
res1, lat1 = ask("Can you browse example.com and summarize what is on the page?")
print(f"Latency: {lat1:.2f}s")
print(f"Task State: {res1.get('task_state')}")
print(f"Blocked Reason: {res1.get('blocked_reason')}")
print(f"Reply: {res1.get('answer')}")

print("\n=== Query 2: Search the web using headless browser for latest news on Mars rover ===")
res2, lat2 = ask("Search the web using headless browser for latest news on Mars rover")
print(f"Latency: {lat2:.2f}s")
print(f"Task State: {res2.get('task_state')}")
print(f"Blocked Reason: {res2.get('blocked_reason')}")
print(f"Reply: {res2.get('answer')}")

print("\n=== Query 3: Run a bash command to check system uptime on tv-mum-01 ===")
res3, lat3 = ask("Run a bash command to check system uptime on tv-mum-01")
print(f"Latency: {lat3:.2f}s")
print(f"Task State: {res3.get('task_state')}")
print(f"Blocked Reason: {res3.get('blocked_reason')}")
print(f"Reply: {res3.get('answer')}")

print("\n=======================================================")
print("  LIVE CONVERSATIONAL TESTS COMPLETED!                ")
print("=======================================================")
