"""Layla Coder Plugin -- Autonomous Software Engineer Worker (Pillar 6: OpenHands).

Enables Layla to dispatch background software engineering tasks, execute unit tests,
diagnose stack traces, and iterate on multi-turn code repairs securely on tv-mum-01.

Tools:
  - dispatch_coding_task(description, target_dir="/opt/scientist/src", test_command="", max_iterations=3)
  - check_coding_task(task_id)

Kill switch: OPENHANDS_CODER=0 in /opt/layla/.env. Never raises into the caller.
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
TIMEOUT_SECS = 90

_D: Dict[str, Any] = {}
_lock = threading.Lock()


def enabled() -> bool:
    """Kill switch: OPENHANDS_CODER=0 in /opt/layla/.env turns Coder capability off."""
    return os.environ.get("OPENHANDS_CODER", "1") != "0"


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
        "User-Agent": "Layla-Brain/Coder-1.0",
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

def dispatch_coding_task(
    description: str,
    target_dir: str = "/opt/scientist/src",
    test_command: str = "",
    max_iterations: int = 3,
) -> dict:
    """Dispatches an autonomous software engineering task on tv-mum-01.
    Runs tests, inspects failures, and iterates autonomously.
    """
    if not description:
        return {"status": "error", "error": "Description parameter is required."}

    payload = {
        "description": description,
        "target_dir": target_dir or "/opt/scientist/src",
        "test_command": test_command or None,
        "max_iterations": max(1, min(int(max_iterations), 5)),
    }

    code, resp, err = _http_request("POST", "/api/coder/task", payload, timeout=120)
    if err or code != 200 or not isinstance(resp, dict):
        return {"status": "error", "error": err or f"HTTP {code} from coder service"}

    return {
        "status": "success",
        "task_id": resp.get("task_id"),
        "task_status": resp.get("status"),
        "iterations": resp.get("iterations", 1),
        "log": resp.get("log", ""),
        "error": resp.get("error"),
        "latency_ms": resp.get("latency_ms", 0),
    }


def check_coding_task(task_id: str) -> dict:
    """Checks the status and full execution log of an OpenHands software engineering task."""
    if not task_id:
        return {"status": "error", "error": "task_id is required."}

    safe_id = urllib.parse.quote(task_id)
    code, resp, err = _http_request("GET", f"/api/coder/task/{safe_id}", timeout=20)
    if err or code != 200 or not isinstance(resp, dict):
        return {"status": "error", "error": err or f"HTTP {code} from coder service"}

    return resp


# ---------------- Tool Schemas & Definitions ----------------

DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "dispatch_coding_task",
            "description": "Dispatch an autonomous software engineering loop to fix bugs, refactor code, or run test suites in a persistent sandbox on tv-mum-01.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "Goal or description of what code to write, test, or repair."},
                    "target_dir": {"type": "string", "description": "Target repository or directory (default /opt/scientist/src)."},
                    "test_command": {"type": "string", "description": "Bash command to verify the codebase (e.g. pytest, python test.py)."},
                    "max_iterations": {"type": "integer", "description": "Max diagnostic repair attempts (default 3, range 1-5)."},
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_coding_task",
            "description": "Check the status, test iterations, and detailed execution logs of a previously dispatched coding task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID returned by dispatch_coding_task (e.g. coder-xxxx)."},
                },
                "required": ["task_id"],
            },
        },
    },
]

TOOLS = DEFINITIONS
NAMES = ["dispatch_coding_task", "check_coding_task"]

KEYWORDS = [
    "code fix", "software engineer", "refactor", "openhands", "coding task", "fix bug",
    "unit test", "write code", "diagnostic loop", "coder", "debug code", "patch code"
]


# ---------------- Plugin Lifecycle & Dispatch ----------------

def init(**deps: Any) -> None:
    with _lock:
        _D.update(deps)
    print("[coder] layla_coder plugin initialized", flush=True)


def turn_hint(message: str) -> Optional[str]:
    """Provides situational awareness hint if query involves autonomous coding tasks."""
    if not enabled():
        return None
    msg = (message or "").lower()
    if any(k in msg for k in ("fix bug", "refactor", "coding task", "software engineer", "openhands", "write unit test")):
        return "You have an autonomous software engineer loop (dispatch_coding_task, check_coding_task) on tv-mum-01."
    return None


def call(name: str, args: Optional[dict] = None) -> dict:
    args = args or {}
    try:
        if not enabled():
            return {"status": "error", "error": "Coder capability is disabled."}
        if name == "dispatch_coding_task":
            return dispatch_coding_task(
                description=args.get("description", ""),
                target_dir=args.get("target_dir", "/opt/scientist/src"),
                test_command=args.get("test_command", ""),
                max_iterations=int(args.get("max_iterations", 3)),
            )
        if name == "check_coding_task":
            return check_coding_task(args.get("task_id", ""))
        return {"status": "error", "error": f"Unknown coder tool: {name}"}
    except Exception as exc:
        return {"status": "error", "error": f"Error running {name}: {type(exc).__name__}: {exc}"}
