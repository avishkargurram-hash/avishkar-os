"""Layla Interpreter Plugin -- Self-Healing Terminal & Code Loop (Pillar 8).

Enables Layla to execute bash shell commands, system utilities, and Python scripts
with autonomous error diagnosis and single-step repair loops (up to 3 bounded retries)
executed securely on tv-mum-01.

Tools:
  - run_terminal_command(command, language="bash")
  - run_self_healing_script(code, language="python")

Kill switch: OPEN_INTERPRETER=0 in /opt/layla/.env. Never raises into the caller.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

# Configuration with environment defaults
DEFAULT_API_URL = "http://103.168.22.202:8095"
DEFAULT_API_TOKEN = ""
TIMEOUT_SECS = 75

_D: Dict[str, Any] = {}
_lock = threading.Lock()


def enabled() -> bool:
    """Kill switch: OPEN_INTERPRETER=0 in /opt/layla/.env turns Interpreter integration off."""
    return os.environ.get("OPEN_INTERPRETER", "1") != "0"


def _get_config() -> dict[str, str]:
    return {
        "api_url": os.environ.get("SCIENTIST_API_URL", DEFAULT_API_URL).rstrip("/"),
        "token": os.environ.get("SCIENTIST_API_TOKEN", DEFAULT_API_TOKEN).strip(),
    }


def _http_request(method: str, path: str, payload: Optional[dict] = None, timeout: int = TIMEOUT_SECS) -> tuple[int, Any, Optional[str]]:
    """Makes an authenticated HTTP request to the Scientist/Interpreter API service.
    Returns (status_code, parsed_json_or_text, error_message).
    Never raises exceptions.
    """
    conf = _get_config()
    url = f"{conf['api_url']}{path}"
    headers = {
        "Authorization": f"Bearer {conf['token']}",
        "User-Agent": "Layla-Brain/Interpreter-1.0",
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

def run_terminal_command(command: str, language: str = "bash") -> dict:
    """Run a bash shell command or terminal script on tv-mum-01 with automatic error capture and self-healing loop."""
    if not command:
        return {"status": "error", "error": "Command parameter is required."}

    code, resp, err = _http_request("POST", "/api/interpreter/run", {
        "command": command,
        "language": language or "bash",
        "max_retries": 3,
        "timeout_s": 30.0,
    }, timeout=60)

    if err or code != 200 or not isinstance(resp, dict):
        return {"status": "error", "error": err or f"HTTP {code} from interpreter service"}

    status = resp.get("status", "error")
    attempts = resp.get("attempts", 1)
    output = resp.get("output", "")
    history = resp.get("history", [])
    latency_ms = resp.get("latency_ms", 0)

    repairs = [h.get("repair_action") for h in history if h.get("repair_action")]
    header = f"Command: {command} (attempts: {attempts}, time: {latency_ms}ms)\n"
    if repairs:
        header += "Self-Healing Repairs Applied:\n" + "\n".join(f"- {r}" for r in repairs) + "\n\n"
    header += f"Output:\n{output or resp.get('error', '(no output)')}"

    return {
        "status": status,
        "attempts": attempts,
        "output": header,
        "raw_output": output,
        "repairs": repairs,
        "history": history,
        "latency_ms": latency_ms,
        "error": resp.get("error") if status != "success" else None,
    }


def run_self_healing_script(code: str, language: str = "python") -> dict:
    """Execute a Python script or command loop with autonomous self-healing,
    missing dependency auto-installation, and parent directory creation.
    """
    if not code:
        return {"status": "error", "error": "Code parameter is required."}

    http_code, resp, err = _http_request("POST", "/api/interpreter/run", {
        "command": code,
        "language": language or "python",
        "max_retries": 3,
        "timeout_s": 35.0,
    }, timeout=70)

    if err or http_code != 200 or not isinstance(resp, dict):
        return {"status": "error", "error": err or f"HTTP {http_code} from interpreter service"}

    status = resp.get("status", "error")
    attempts = resp.get("attempts", 1)
    output = resp.get("output", "")
    history = resp.get("history", [])
    latency_ms = resp.get("latency_ms", 0)

    repairs = [h.get("repair_action") for h in history if h.get("repair_action")]
    summary = f"Script Execution (attempts: {attempts}, time: {latency_ms}ms)\n"
    if repairs:
        summary += "Self-Healing Actions:\n" + "\n".join(f"- {r}" for r in repairs) + "\n\n"
    summary += f"Result:\n{output or resp.get('error', '(no output)')}"

    return {
        "status": status,
        "attempts": attempts,
        "output": summary,
        "raw_output": output,
        "repairs": repairs,
        "history": history,
        "latency_ms": latency_ms,
        "error": resp.get("error") if status != "success" else None,
    }


# ---------------- Schema & Tool Definitions ----------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_terminal_command",
            "description": "Run a bash shell command or terminal script on tv-mum-01 with automatic error capture, system diagnostics, and self-healing loop.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The bash shell command line string to execute."},
                    "language": {"type": "string", "enum": ["bash", "sh"], "description": "Script language (default bash)."},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_self_healing_script",
            "description": "Execute a Python script or code block on tv-mum-01 with autonomous self-healing, automatic dependency resolution, and auto-repairing retries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "The Python source code to execute."},
                    "language": {"type": "string", "enum": ["python", "bash"], "description": "Programming language (default python)."},
                },
                "required": ["code"],
            },
        },
    },
]

NAMES = ["run_terminal_command", "run_self_healing_script"]

KEYWORDS = [
    "terminal", "bash", "run command", "shell script", "python script", "execute code",
    "self-healing", "interpreter", "command line", "run script", "execute command",
    "shell", "run bash", "run python", "system command", "cli"
]


# ---------------- Plugin Lifecycle & Dispatch ----------------

def init(**deps: Any) -> None:
    with _lock:
        _D.update(deps)
    print("[interpreter] layla_interpreter plugin initialized", flush=True)


def turn_hint(message: str) -> Optional[str]:
    """Provides situational awareness hint if query involves running commands or scripts."""
    if not enabled():
        return None
    msg = (message or "").lower()
    if any(k in msg for k in ("run command", "bash", "terminal", "python script", "execute code", "shell")):
        return "You have autonomous self-healing execution loops (run_terminal_command, run_self_healing_script) on tv-mum-01."
    return None


def call(name: str, args: Optional[dict] = None) -> dict:
    args = args or {}
    try:
        if not enabled():
            return {"status": "error", "error": "Interpreter capability is disabled."}
        if name == "run_terminal_command":
            return run_terminal_command(args.get("command", ""), args.get("language", "bash"))
        if name == "run_self_healing_script":
            return run_self_healing_script(args.get("code", ""), args.get("language", "python"))
        return {"status": "error", "error": f"Unknown interpreter tool: {name}"}
    except Exception as exc:
        return {"status": "error", "error": f"Error running {name}: {type(exc).__name__}: {exc}"}
