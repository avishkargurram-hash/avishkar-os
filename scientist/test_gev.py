import json, urllib.request

req = urllib.request.Request(
    'http://127.0.0.1:4173/mcp',
    data=json.dumps({
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'tools/call',
        'params': {'name': 'show_in_gods_eye_view', 'arguments': {'place': 'Taiwan'}}
    }).encode(),
    headers={
        'Content-Type': 'application/json',
        'X-GEV-Key': 'd53a5c29fd677344dcc67a8e8cf1854dd7a9a9af5ed64e52abb2a641eb61da48'
    }
)
try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
        print(json.dumps(data, indent=2))
except Exception as e:
    print("Error:", e)
