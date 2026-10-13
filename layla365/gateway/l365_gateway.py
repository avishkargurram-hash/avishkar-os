"""Layla 365 Agent Gateway (runs inside the Oracle brain process).

Lets the nine Layla-365 agents on tv-mum-01 call a NAMED allowlist of the
brain's tools. Defense in depth: nginx IP allowlist -> source-IP check ->
per-agent token (only a sha256 is stored here) -> per-agent tool allowlist ->
per-agent rate limit -> audit line for every call. Kill switch: create the
file /opt/layla/l365_gateway.disabled (takes effect immediately).
"""
import hashlib
import hmac
import json
import os
import threading
import time

CONF = "/opt/layla/l365_gateway.json"
KILL = "/opt/layla/l365_gateway.disabled"
LOG = "/opt/layla/l365_gateway.log"

_lock = threading.Lock()
_hits = {}
_cache = {"mt": None, "conf": {}}


def _conf():
    try:
        mt = os.path.getmtime(CONF)
    except OSError:
        return {}
    if mt != _cache["mt"]:
        with open(CONF, encoding="utf-8") as f:
            _cache["conf"] = json.load(f)
        _cache["mt"] = mt
    return _cache["conf"]


def _client_ip(h):
    peer = h.client_address[0]
    if peer in ("127.0.0.1", "::1"):          # only nginx on loopback may vouch for the real IP
        return (h.headers.get("X-Real-IP") or peer).strip()
    return peer


def _audit(rec):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def handle(h, data, execute_tool):
    t0 = time.time()
    ip = _client_ip(h)
    agent = (h.headers.get("X-L365-Agent") or "").strip().lower()
    body = data if isinstance(data, dict) else {}
    tool = str(body.get("tool", "")).strip()
    args = body.get("args") or {}

    def done(code, obj, why=""):
        _audit({"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "agent": agent, "ip": ip, "tool": tool,
                "code": code, "why": why, "ms": int((time.time() - t0) * 1000)})
        return h._json(code, obj)

    if os.path.exists(KILL):
        return done(503, {"error": "gateway disabled"}, "kill-switch")
    c = _conf()
    if not c:
        return done(503, {"error": "gateway not configured"}, "no-config")
    if ip not in c.get("allowed_ips", []):
        return done(403, {"error": "forbidden"}, "ip")
    spec = (c.get("agents") or {}).get(agent)
    tok = h.headers.get("X-L365-Token", "")
    expected = (spec or {}).get("token_sha256", "")
    if not spec or not hmac.compare_digest(hashlib.sha256(tok.encode()).hexdigest(), expected):
        return done(401, {"error": "unauthorized"}, "token")
    if tool not in spec.get("allow", []):
        return done(403, {"error": "tool not allowed for this agent"}, "allowlist")
    if not isinstance(args, dict):
        return done(400, {"error": "args must be an object"}, "bad-args")
    now = time.time()
    limit = int(spec.get("rate_per_min", 30))
    with _lock:
        window = [x for x in _hits.get(agent, []) if now - x < 60]
        if len(window) >= limit:
            _hits[agent] = window
            return done(429, {"error": "rate limited"}, "rate")
        window.append(now)
        _hits[agent] = window
    try:
        res = execute_tool(tool, args)
        res = json.loads(json.dumps(res, default=str))
    except Exception as e:  # noqa: BLE001
        return done(500, {"error": f"{type(e).__name__}"}, "exception")
    return done(200, {"ok": True, "result": res}, "ok")
