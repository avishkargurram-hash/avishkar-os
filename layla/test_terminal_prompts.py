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

test_prompts = [
    "Execute terminal command: uptime",
    "Use run_terminal_command to check uptime on tv-mum-01",
    "Run terminal command 'uname -a'",
]

for p in test_prompts:
    print(f"\n--- Testing Prompt: {p} ---")
    res, lat = ask(p)
    print(f"Latency: {lat:.2f}s")
    print(f"Reply: {res.get('answer')}")
    print(f"Task State: {res.get('task_state')}")
