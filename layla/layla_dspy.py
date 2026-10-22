"""Layla DSPy Plugin -- Offline Prompt & Signature Optimizer (Pillar 3: DSPy).

Enables Layla to compile, cache, and retrieve quantitatively optimized few-shot exemplars
and prompt signatures for executive routing and tool-use domains.

Tools:
  - compile_prompt_optimizer(domain="all")
  - get_optimized_prompts(domain="all")

Kill switch: DSPY_OPTIMIZER=0 in /opt/layla/.env. Never raises into the caller.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

DEFAULT_API_URL = "http://103.168.22.202:8095"
DEFAULT_API_TOKEN = ""
TIMEOUT_SECS = 45

_D: Dict[str, Any] = {}
_lock = threading.Lock()


def enabled() -> bool:
    """Kill switch: DSPY_OPTIMIZER=0 in /opt/layla/.env turns DSPy capability off."""
    return os.environ.get("DSPY_OPTIMIZER", "1") != "0"


def _get_config() -> dict[str, str]:
    return {
        "api_url": os.environ.get("SCIENTIST_API_URL", DEFAULT_API_URL).rstrip("/"),
        "token": os.environ.get("SCIENTIST_API_TOKEN", DEFAULT_API_TOKEN).strip(),
    }


def _http_request(method: str, path: str, payload: Optional[dict] = None, timeout: int = TIMEOUT_SECS) -> tuple[int, Any, Optional[str]]:
    """Makes an authenticated HTTP request to the Scientist OS API service.
    Returns (status_code, parsed_json_or_text, error_message).
    Never raises exceptions.
    """
    conf = _get_config()
    url = f"{conf['api_url']}{path}"
    headers = {
        "Authorization": f"Bearer {conf['token']}",
        "User-Agent": "Layla-Brain/DSPy-1.0",
        "Content-Type": "application/json",
    }
    data_bytes = None
    if payload is not None:
        try:
            data_bytes = json.dumps(payload).encode("utf-8")
        except Exception as exc:
            return 0, None, f"JSON serialization error: {exc}"

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(raw)
            except Exception:
                data = raw
            return resp.status, data, None
    except urllib.error.HTTPError as exc:
        raw_err = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        return exc.code, None, f"HTTP {exc.code}: {raw_err}"
    except urllib.error.URLError as exc:
        return 0, None, f"Connection failed to {url}: {exc.reason}"
    except Exception as exc:
        return 0, None, f"Request exception: {type(exc).__name__}: {exc}"


# ---------------- Tool Implementations ----------------

def compile_prompt_optimizer(domain: str = "all") -> dict:
    """Compiles optimized few-shot exemplars and routing prompt signatures for a specific domain or all domains."""
    code, resp, err = _http_request("POST", "/api/dspy/compile", {"domain": domain or "all"}, timeout=30)
    if err or code != 200 or not isinstance(resp, dict):
        return {"status": "error", "error": err or f"HTTP {code} from DSPy service"}

    return {
        "status": "success",
        "domains_compiled": resp.get("domains_compiled", []),
        "latency_ms": resp.get("latency_ms", 0),
        "results": resp.get("results", {}),
    }


def get_optimized_prompts(domain: str = "all") -> dict:
    """Retrieves compiled few-shot exemplars, signatures, and evaluation metrics for a domain."""
    safe_domain = urllib.parse.quote(domain or "all")
    code, resp, err = _http_request("GET", f"/api/dspy/prompts?domain={safe_domain}", timeout=20)
    if err or code != 200 or not isinstance(resp, dict):
        return {"status": "error", "error": err or f"HTTP {code} from DSPy service"}

    return resp


# ---------------- Tool Schemas & Definitions ----------------

DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "compile_prompt_optimizer",
            "description": "Trigger offline compilation of prompt signatures and few-shot exemplars for Layla's tools using DSPy teleprompter logic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "Domain to compile (worldstate, hindsight, browser, interpreter, or all)."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_optimized_prompts",
            "description": "Fetch quantitatively compiled few-shot exemplars and prompt signatures to boost reasoning accuracy.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "Domain to retrieve (worldstate, hindsight, browser, interpreter, or all)."},
                },
            },
        },
    },
]

TOOLS = DEFINITIONS
NAMES = ["compile_prompt_optimizer", "get_optimized_prompts"]

KEYWORDS = [
    "dspy", "prompt optimization", "compile prompt", "few-shot", "optimizer",
    "exemplars", "signature", "eval metric", "prompt signature", "teleprompter"
]


# ---------------- Plugin Lifecycle & Dispatch ----------------

def init(**deps: Any) -> None:
    with _lock:
        _D.update(deps)
    print("[dspy] layla_dspy plugin initialized", flush=True)


def turn_hint(message: str) -> Optional[str]:
    """Provides situational awareness hint if query involves prompt compilation or DSPy."""
    if not enabled():
        return None
    msg = (message or "").lower()
    if any(k in msg for k in ("dspy", "compile prompt", "prompt optimization", "few-shot exemplars")):
        return "You have offline prompt compilation and exemplar optimization (compile_prompt_optimizer, get_optimized_prompts)."
    return None


def call(name: str, args: Optional[dict] = None) -> dict:
    args = args or {}
    try:
        if not enabled():
            return {"status": "error", "error": "DSPy optimizer capability is disabled."}
        if name == "compile_prompt_optimizer":
            return compile_prompt_optimizer(domain=args.get("domain", "all"))
        if name == "get_optimized_prompts":
            return get_optimized_prompts(domain=args.get("domain", "all"))
        return {"status": "error", "error": f"Unknown dspy tool: {name}"}
    except Exception as exc:
        return {"status": "error", "error": f"Error running {name}: {type(exc).__name__}: {exc}"}
