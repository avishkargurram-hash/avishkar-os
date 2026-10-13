"""Small shared helpers for the Task-1 capability plugins (#3-#11).

Kept dependency-free (stdlib only) so every plugin can import it without
touching layla_service.py. Never prints secrets.
"""
import datetime as _dt
import json
import os
import re
import urllib.request
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
UA = "layla/1.0"   # Cerebras/Evolviot answer 403 to python-urllib's default UA


def now_ist():
    return _dt.datetime.now(IST)


def fmt_ts(ts):
    return _dt.datetime.fromtimestamp(ts, IST).strftime("%a %d %b %I:%M %p").replace(" 0", " ")


def flag(name, default="1"):
    """Kill switches: <NAME>=0 in /opt/layla/.env turns a capability off."""
    return os.environ.get(name, default) != "0"


def llm(system, user, max_tokens=600, temperature=0.2, model=None):
    key = os.environ.get("CEREBRAS_API_KEY", "")
    if not key:
        raise RuntimeError("no CEREBRAS_API_KEY")
    body = {"model": model or os.environ.get("PLUGIN_MODEL", "gpt-oss-120b"),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": max_tokens, "temperature": temperature, "reasoning_effort": "low"}
    req = urllib.request.Request("https://api.cerebras.ai/v1/chat/completions",
                                 data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                          "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        d = json.loads(r.read())
    return (d["choices"][0]["message"].get("content") or "").strip()


def parse_json(raw):
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip())
    m = re.search(r"[\{\[].*[\}\]]", raw, re.S)
    return json.loads(m.group(0) if m else raw)


def llm_json(system, user, max_tokens=600):
    return parse_json(llm(system, user, max_tokens=max_tokens))


def tool(name, desc, props=None, req=None):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props or {}, "required": req or []}}}


S = {"type": "string"}
I = {"type": "integer"}
B = {"type": "boolean"}
