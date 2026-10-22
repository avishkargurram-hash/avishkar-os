"""Layla RSI Plugin -- Recursive Self-Improvement Approval Gate (Pillar 9: RSI-Gate).

Enables Layla to propose self-modifications, inspect proposed patches, and require
strict cryptographic human authorization before any production deployment.

Tools:
  - propose_self_improvement(target_component, title, rationale, code_diff)
  - list_rsi_proposals(status=None)
  - decide_rsi_proposal(proposal_id, decision, auth_token, rejection_reason="")

Kill switch: RSI_GATE=0 in /opt/layla/.env. Never raises into the caller.
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
    """Kill switch: RSI_GATE=0 in /opt/layla/.env turns RSI capability off."""
    return os.environ.get("RSI_GATE", "1") != "0"


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
        "User-Agent": "Layla-Brain/RSI-1.0",
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

def propose_self_improvement(
    target_component: str,
    title: str,
    rationale: str,
    code_diff: str,
) -> dict:
    """Drafts an improvement proposal in the sandboxed staging environment on tv-mum-01.
    All proposals are physically locked in PENDING_HUMAN status until cryptographic creator sign-off.
    """
    if not target_component or not title or not code_diff:
        return {"status": "error", "error": "target_component, title, and code_diff are required."}

    payload = {
        "target_component": target_component,
        "title": title,
        "rationale": rationale or "Autonomous optimization proposal",
        "code_diff": code_diff,
    }

    code, resp, err = _http_request("POST", "/api/rsi/propose", payload, timeout=30)
    if err or code != 200 or not isinstance(resp, dict):
        return {"status": "error", "error": err or f"HTTP {code} from RSI service"}

    return {
        "status": "success",
        "proposal_id": resp.get("proposal_id"),
        "proposal_status": resp.get("proposal_status", "PENDING_HUMAN"),
        "title": resp.get("title"),
        "target_component": resp.get("target_component"),
        "patch_file": resp.get("patch_file"),
        "note": "Proposal is safely staged in sandbox. It requires human creator approval before deployment.",
    }


def list_rsi_proposals(status: Optional[str] = None) -> dict:
    """Lists self-improvement proposals currently in the staging sandbox."""
    path = "/api/rsi/proposals"
    if status:
        path += f"?status={urllib.parse.quote(status)}"

    code, resp, err = _http_request("GET", path, timeout=20)
    if err or code != 200 or not isinstance(resp, dict):
        return {"status": "error", "error": err or f"HTTP {code} from RSI service"}

    return resp


def decide_rsi_proposal(
    proposal_id: str,
    decision: str,
    auth_token: str,
    rejection_reason: str = "",
) -> dict:
    """Applies human decision (APPROVE or REJECT) on a self-improvement proposal.
    Requires the creator's cryptographic secret authorization token.
    """
    if not proposal_id or not decision:
        return {"status": "error", "error": "proposal_id and decision are required."}

    payload = {
        "proposal_id": proposal_id,
        "decision": decision.upper(),
        "auth_token": auth_token or "",
        "rejection_reason": rejection_reason or None,
    }

    code, resp, err = _http_request("POST", "/api/rsi/decide", payload, timeout=30)
    if err or code != 200 or not isinstance(resp, dict):
        return {"status": "error", "error": err or f"HTTP {code} from RSI service"}

    return resp


# ---------------- Tool Schemas & Definitions ----------------

DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "propose_self_improvement",
            "description": "Draft a self-improvement proposal and sandboxed code diff. Automatically gated under PENDING_HUMAN status awaiting explicit creator approval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_component": {"type": "string", "description": "Target component (e.g. router, prompt, hindsight, tools)."},
                    "title": {"type": "string", "description": "Short summary of the improvement."},
                    "rationale": {"type": "string", "description": "Evidence and metric justifications for the change."},
                    "code_diff": {"type": "string", "description": "Unified diff format patch for the proposed change."},
                },
                "required": ["target_component", "title", "code_diff"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_rsi_proposals",
            "description": "List self-improvement proposals across PENDING_HUMAN, APPROVED_DEPLOYED, or REJECTED states.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["PENDING_HUMAN", "APPROVED_DEPLOYED", "REJECTED"], "description": "Filter by status."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "decide_rsi_proposal",
            "description": "Execute human creator sign-off on a self-improvement proposal using cryptographic token validation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "proposal_id": {"type": "string", "description": "Proposal ID to approve or reject."},
                    "decision": {"type": "string", "enum": ["APPROVE", "REJECT"], "description": "Decision action."},
                    "auth_token": {"type": "string", "description": "Human creator master secret token."},
                    "rejection_reason": {"type": "string", "description": "Optional reason if rejecting."},
                },
                "required": ["proposal_id", "decision", "auth_token"],
            },
        },
    },
]

TOOLS = DEFINITIONS
NAMES = ["propose_self_improvement", "list_rsi_proposals", "decide_rsi_proposal"]

KEYWORDS = [
    "rsi", "recursive self-improvement", "self improvement", "propose improvement",
    "rsi proposal", "approval gate", "code patch", "propose patch", "creator sign-off"
]


# ---------------- Plugin Lifecycle & Dispatch ----------------

def init(**deps: Any) -> None:
    with _lock:
        _D.update(deps)
    print("[rsi] layla_rsi plugin initialized", flush=True)


def turn_hint(message: str) -> Optional[str]:
    """Provides situational awareness hint if query involves self-improvement or proposals."""
    if not enabled():
        return None
    msg = (message or "").lower()
    if any(k in msg for k in ("self improvement", "rsi", "propose patch", "propose improvement", "rsi proposal")):
        return "You have a sandboxed Recursive Self-Improvement approval gate (propose_self_improvement, list_rsi_proposals, decide_rsi_proposal)."
    return None


def call(name: str, args: Optional[dict] = None) -> dict:
    args = args or {}
    try:
        if not enabled():
            return {"status": "error", "error": "RSI capability is disabled."}
        if name == "propose_self_improvement":
            return propose_self_improvement(
                target_component=args.get("target_component", ""),
                title=args.get("title", ""),
                rationale=args.get("rationale", ""),
                code_diff=args.get("code_diff", ""),
            )
        if name == "list_rsi_proposals":
            return list_rsi_proposals(status=args.get("status"))
        if name == "decide_rsi_proposal":
            return decide_rsi_proposal(
                proposal_id=args.get("proposal_id", ""),
                decision=args.get("decision", ""),
                auth_token=args.get("auth_token", ""),
                rejection_reason=args.get("rejection_reason", ""),
            )
        return {"status": "error", "error": f"Unknown rsi tool: {name}"}
    except Exception as exc:
        return {"status": "error", "error": f"Error running {name}: {type(exc).__name__}: {exc}"}
