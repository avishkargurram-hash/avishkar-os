"""Layla Hindsight Plugin -- Experiential Reflection Memory Engine (Pillar 1).

Learns from tool execution outcomes (successes, errors, latency) across all sessions,
stores distilled operational reflections in PostgreSQL on tv-mum-01, and proactively
injects contextual lessons into prompt assembly to prevent repeated mistakes.

Tools:
  - get_hindsight_lessons(domain="general", query="")
  - record_learned_lesson(domain, pattern, intent, trigger_condition, lesson)

Helpers:
  - log_tool_outcome(...) (asynchronous non-blocking telemetry hook)
  - turn_hint(message) (instant in-memory reflection injection)

Kill switch: HINDSIGHT=0 in /opt/layla/.env. Never raises into the caller.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

# Configuration with environment defaults
DEFAULT_API_URL = "http://103.168.22.202:8095"
DEFAULT_API_TOKEN = ""
TIMEOUT_SECS = 15

_D: Dict[str, Any] = {}
_lock = threading.Lock()

# In-memory cached reflection rules for zero-latency turn_hint matching
_cached_rules: List[dict] = []
_last_cache_refresh: float = 0.0
_CACHE_TTL_SECS = 60.0


def enabled() -> bool:
    """Kill switch: HINDSIGHT=0 in /opt/layla/.env turns Hindsight integration off."""
    return os.environ.get("HINDSIGHT", "1") != "0"


def _get_config() -> dict[str, str]:
    return {
        "api_url": os.environ.get("SCIENTIST_API_URL", DEFAULT_API_URL).rstrip("/"),
        "token": os.environ.get("SCIENTIST_API_TOKEN", DEFAULT_API_TOKEN).strip(),
    }


def _http_request(method: str, path: str, payload: Optional[dict] = None) -> tuple[int, Any, Optional[str]]:
    """Makes an authenticated HTTP request to the Hindsight API service.
    Returns (status_code, parsed_json_or_text, error_message).
    Never raises exceptions.
    """
    conf = _get_config()
    url = f"{conf['api_url']}{path}"
    headers = {
        "Authorization": f"Bearer {conf['token']}",
        "User-Agent": "Layla-Brain/Hindsight-1.0",
        "Content-Type": "application/json",
    }
    data_bytes = None
    if payload is not None:
        try:
            data_bytes = json.dumps(payload).encode("utf-8")
        except Exception as exc:
            return 0, None, f"Failed to serialize payload: {exc}"

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECS) as resp:
            status = resp.status
            body = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = body
            return status, parsed, None
    except urllib.error.HTTPError as he:
        err_body = he.read().decode("utf-8", errors="replace")
        return he.code, None, f"HTTP {he.code}: {err_body}"
    except Exception as exc:
        return 0, None, f"Network error: {type(exc).__name__}: {exc}"


# ---------------- Cache Maintenance ----------------

def _refresh_rule_cache_sync() -> None:
    global _cached_rules, _last_cache_refresh
    if not enabled():
        return
    code, data, err = _http_request("GET", "/api/hindsight/reflections")
    if code == 200 and isinstance(data, list):
        with _lock:
            _cached_rules = data
            _last_cache_refresh = time.monotonic()


def _ensure_cache_fresh() -> None:
    now = time.monotonic()
    if (now - _last_cache_refresh) > _CACHE_TTL_SECS:
        # Trigger background refresh to keep turn_hint non-blocking
        threading.Thread(target=_refresh_rule_cache_sync, daemon=True).start()


# ---------------- Asynchronous Tool Outcome Logger ----------------

def log_tool_outcome(
    tool_name: str,
    output_status: str,
    error_message: Optional[str] = None,
    latency_ms: Optional[float] = None,
    input_params: Optional[dict] = None,
    session_id: Optional[str] = None,
) -> None:
    """Dispatches tool execution telemetry to Hindsight in a non-blocking daemon thread.
    Zero impact on conversational latency.
    """
    if not enabled():
        return

    payload = {
        "session_id": session_id or "layla-executive",
        "tool_name": tool_name,
        "input_params": input_params or {},
        "output_status": output_status.upper(),
        "error_message": str(error_message) if error_message else None,
        "latency_ms": float(latency_ms) if latency_ms is not None else None,
    }

    def _worker():
        _http_request("POST", "/api/hindsight/outcomes", payload)

    threading.Thread(target=_worker, daemon=True).start()


# ---------------- Tool Implementations ----------------

def get_hindsight_lessons(domain: str = "general", query: Optional[str] = None) -> dict:
    """Retrieve learned experiential lessons and anti-patterns."""
    if not enabled():
        return {"status": "error", "error": "Hindsight capability is currently disabled (HINDSIGHT=0)."}

    params = []
    if domain and domain.lower() != "all":
        params.append(f"domain={urllib.parse.quote(domain.strip())}")
    if query:
        params.append(f"q={urllib.parse.quote(query.strip())}")
    qs = ("?" + "&".join(params)) if params else ""

    code, data, err = _http_request("GET", f"/api/hindsight/reflections{qs}")
    if err or code != 200 or not isinstance(data, list):
        return {"status": "error", "error": f"Failed to retrieve reflection rules: {err}"}

    lines = []
    for r in data:
        lines.append(f"- [{r.get('domain', 'general').upper()}] Pattern '{r.get('pattern')}': {r.get('lesson')} (Successes: {r.get('success_count', 0)}, Failures: {r.get('failure_count', 0)})")

    out_str = f"Hindsight Lessons ({len(data)} total):\n" + ("\n".join(lines) if lines else "No lessons matching criteria.")
    return {
        "status": "success",
        "count": len(data),
        "lessons": data,
        "output": out_str,
    }


def record_learned_lesson(domain: str, pattern: str, intent: str, trigger_condition: str, lesson: str) -> dict:
    """Record a newly distilled operational lesson learned from execution."""
    if not enabled():
        return {"status": "error", "error": "Hindsight capability is currently disabled."}
    if not pattern or not lesson:
        return {"status": "error", "error": "pattern and lesson are required."}

    payload = {
        "domain": (domain or "general").lower().strip(),
        "pattern": pattern.strip(),
        "intent": intent.strip(),
        "trigger_condition": trigger_condition.strip(),
        "lesson": lesson.strip(),
    }
    code, data, err = _http_request("POST", "/api/hindsight/reflections", payload)
    if err or code not in (200, 201):
        return {"status": "error", "error": f"Failed to record reflection rule: {err}"}

    # Refresh local cache
    threading.Thread(target=_refresh_rule_cache_sync, daemon=True).start()

    return {
        "status": "success",
        "lesson_id": (data.get("rule") or {}).get("id"),
        "output": f"Learned lesson recorded: '{lesson}' for pattern '{pattern}'.",
    }


# ---------------- OpenAI Function Tool Schemas ----------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_hindsight_lessons",
            "description": "Consult the experiential reflection memory engine for lessons learned from past successes, failures, and anti-patterns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "enum": ["all", "general", "science", "hardware", "browser", "code", "system"],
                        "description": "Operational domain (default 'general').",
                    },
                    "query": {
                        "type": "string",
                        "description": "Optional search keyword to match against past error patterns or intents.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_learned_lesson",
            "description": "Save an operational reflection rule after discovering an error or friction point, ensuring Layla never repeats the mistake.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "enum": ["general", "science", "hardware", "browser", "code", "system"], "description": "Operational domain."},
                    "pattern": {"type": "string", "description": "Keyword or regex pattern that triggers this lesson."},
                    "intent": {"type": "string", "description": "Summary of the action that was attempted."},
                    "trigger_condition": {"type": "string", "description": "Failure mode or anti-pattern observed."},
                    "lesson": {"type": "string", "description": "Actionable prompt instruction to avoid repeating the mistake."},
                },
                "required": ["domain", "pattern", "intent", "trigger_condition", "lesson"],
            },
        },
    },
]

NAMES = ["get_hindsight_lessons", "record_learned_lesson"]

KEYWORDS = [
    "lesson", "lessons", "learned", "past mistake", "avoid mistake",
    "hindsight", "anti-pattern", "past errors", "reflection", "reflection rules"
]


# ---------------- Plugin Lifecycle & Dispatch ----------------

def init(**deps: Any) -> None:
    with _lock:
        _D.update(deps)
    print("[hindsight] layla_hindsight plugin initialized", flush=True)
    # Eager initial load of reflection rules
    threading.Thread(target=_refresh_rule_cache_sync, daemon=True).start()


def turn_hint(message: str) -> Optional[str]:
    """Proactively injects matched experiential lessons into conversational context."""
    if not enabled():
        return None
    _ensure_cache_fresh()

    msg = (message or "").lower()
    matched_lessons = []
    with _lock:
        for r in _cached_rules:
            pat = r.get("pattern", "").lower()
            if pat and pat in msg:
                matched_lessons.append(r.get("lesson"))

    if matched_lessons:
        # Deduplicate and return concise advice
        unique_lessons = list(dict.fromkeys(matched_lessons))[:2]
        return "Hindsight Operational Guidance: " + " ".join(unique_lessons)

    if any(k in msg for k in ("lesson", "learned", "past error", "avoid mistake", "hindsight")):
        return "You have access to experiential reflection memory (get_hindsight_lessons, record_learned_lesson)."
    return None


def call(name: str, args: Optional[dict] = None) -> dict:
    args = args or {}
    try:
        if not enabled():
            return {"status": "error", "error": "Hindsight capability is disabled."}
        if name == "get_hindsight_lessons":
            return get_hindsight_lessons(args.get("domain", "general"), args.get("query"))
        if name == "record_learned_lesson":
            return record_learned_lesson(
                args.get("domain", "general"),
                args.get("pattern", ""),
                args.get("intent", ""),
                args.get("trigger_condition", ""),
                args.get("lesson", ""),
            )
        return {"status": "error", "error": f"Unknown hindsight tool: {name}"}
    except Exception as exc:
        return {"status": "error", "error": f"Error running {name}: {type(exc).__name__}: {exc}"}
