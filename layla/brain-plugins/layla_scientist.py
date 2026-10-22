"""Layla Scientist OS Plugin -- Autonomous Scientific Research & Investigation.

Layla acts as the executive client of Scientist OS (running on tv-mum-01).
She can launch deep hypothesis-driven scientific investigations, check live progress,
query finalized verdicts, and present structured Markdown research reports.

Tools:
  - start_scientific_research(question, depth="STANDARD")
  - get_research_status(mission_id)
  - get_research_verdict(mission_id)
  - get_research_report(mission_id, format="markdown")

Kill switch: SCIENTIST=0 in /opt/layla/.env. Never raises into the caller.
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
from typing import Any, Dict, Optional

# Configuration with environment defaults
DEFAULT_SCIENTIST_URL = "http://103.168.22.202:8095"
DEFAULT_SCIENTIST_TOKEN = ""
DEFAULT_WEB_URL = "http://103.168.22.202:8095"
TIMEOUT_SECS = 20

_D: Dict[str, Any] = {}  # memory, push, execute_tool
_lock = threading.Lock()


def enabled() -> bool:
    """Kill switch: SCIENTIST=0 in /opt/layla/.env turns Scientist integration off."""
    return os.environ.get("SCIENTIST", "1") != "0"


def _get_config() -> dict[str, str]:
    return {
        "api_url": os.environ.get("SCIENTIST_API_URL", DEFAULT_SCIENTIST_URL).rstrip("/"),
        "token": os.environ.get("SCIENTIST_API_TOKEN", DEFAULT_SCIENTIST_TOKEN).strip(),
        "web_url": os.environ.get("SCIENTIST_WEB_URL", DEFAULT_WEB_URL).rstrip("/"),
    }


def _http_request(method: str, path: str, payload: Optional[dict] = None) -> tuple[int, Any, Optional[str]]:
    """Makes an authenticated HTTP request to the Scientist OS API service.
    Returns (status_code, parsed_json_or_text, error_message).
    Never raises exceptions.
    """
    conf = _get_config()
    url = f"{conf['api_url']}{path}"
    headers = {
        "Authorization": f"Bearer {conf['token']}",
        "User-Agent": "Layla-Brain/1.0",
        "Accept": "application/json",
    }
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECS) as resp:
            raw = resp.read().decode("utf-8")
            status = resp.status
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = raw
            return status, parsed, None
    except urllib.error.HTTPError as he:
        err_body = he.read().decode("utf-8", errors="replace")
        try:
            parsed_err = json.loads(err_body)
            msg = parsed_err.get("detail", err_body)
        except Exception:
            msg = err_body
        return he.code, None, f"HTTP {he.code}: {msg}"
    except urllib.error.URLError as ue:
        return 0, None, f"Network connection error: {ue.reason}"
    except Exception as exc:
        return 0, None, f"{type(exc).__name__}: {exc}"


# ---------------- 4 Executive Tools ----------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "start_scientific_research",
            "description": (
                "Launch a rigorous, multi-agent scientific investigation into an empirical question, "
                "scientific claim, or hypothesis. Scientist OS will formulate falsifiable hypotheses, "
                "search literature, design and run sandboxed code experiments, run replication studies, "
                "subject findings to a Bayesian adversarial critic, and synthesize a formal verdict. "
                "Returns the newly created mission ID."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The exact scientific question or hypothesis to investigate.",
                    },
                    "depth": {
                        "type": "string",
                        "enum": ["QUICK", "STANDARD", "DEEP", "EXHAUSTIVE"],
                        "default": "STANDARD",
                        "description": (
                            "Research depth: QUICK (rapid literature & preliminary test), "
                            "STANDARD (thorough investigation with replications and critic review, default), "
                            "DEEP (extended hypothesis space and replication passes), "
                            "EXHAUSTIVE (maximum iterations and verification)."
                        ),
                    },
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_research_status",
            "description": (
                "Check the real-time execution status of an ongoing or completed scientific research mission. "
                "Returns the current research phase (SCOPING, EXPLORATION, EXPERIMENTATION, SYNTHESIS, COMPLETED), "
                "stage, iteration count, Bayesian confidence score, research questions addressed, and stop reason."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "mission_id": {
                        "type": "string",
                        "description": "The unique ID of the scientific mission (e.g. SCI-...).",
                    },
                },
                "required": ["mission_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_research_verdict",
            "description": (
                "Retrieve the formal synthesized scientific verdict for a research mission. "
                "Returns the verdict label (SUPPORTED, REFUTED, INCONCLUSIVE, LIKELY_SUPPORTED, "
                "LIKELY_NOT_SUPPORTED), confidence score, and a concise plain-English conclusion."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "mission_id": {
                        "type": "string",
                        "description": "The unique ID of the scientific mission (e.g. SCI-...).",
                    },
                },
                "required": ["mission_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_research_report",
            "description": (
                "Retrieve the complete or executive summary research report for a scientific mission. "
                "Includes executive summary, hypotheses evaluated, empirical evidence matrix, "
                "replication outcomes, adversarial critic review, and final verdict with citation references."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "mission_id": {
                        "type": "string",
                        "description": "The unique ID of the scientific mission (e.g. SCI-...).",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["markdown", "json"],
                        "default": "markdown",
                        "description": "The desired format for the report (markdown or json).",
                    },
                },
                "required": ["mission_id"],
            },
        },
    },
]

NAMES = {t["function"]["name"] for t in TOOLS}

KEYWORDS = (
    "research", "investigate", "investigation", "hypothesis", "hypotheses",
    "scientific", "experiment", "experiments", "study whether", "is it true that",
    "prove", "disprove", "scientific research", "scientist", "scientific verdict",
    "research status", "research report", "literature search", "replication",
    "superconductor", "superconductivity", "empirical evidence"
)


# ---------------- Tool Implementations ----------------

def start_scientific_research(question: str, depth: str = "STANDARD") -> dict:
    if not enabled():
        return {"status": "error", "error": "Scientist research system is currently disabled (SCIENTIST=0)."}
    if not question or not question.strip():
        return {"status": "error", "error": "Please provide a valid scientific question or hypothesis."}

    depth = depth.upper() if depth else "STANDARD"
    payload = {"question": question.strip(), "depth": depth, "demo": False}
    code, data, err = _http_request("POST", "/api/missions", payload)
    if err or code not in (200, 201):
        return {
            "status": "error",
            "error": f"The scientific research system could not be reached: {err or f'status {code}'}",
        }

    mid = data.get("id") or data.get("mission_id")
    status = data.get("status", "ACTIVE")
    conf = _get_config()
    dashboard_url = f"{conf['web_url']}/#/missions/{mid}"

    summary = (
        f"Scientific research mission {mid} has been initiated with depth {depth}. "
        f"Initial status is {status}. The investigation will autonomously gather literature, "
        f"execute verified computational experiments, and subject findings to Bayesian critic review. "
        f"Live timeline is available at {dashboard_url}."
    )
    return {
        "status": "success",
        "mission_id": mid,
        "research_status": status,
        "depth": depth,
        "dashboard_url": dashboard_url,
        "output": summary,
    }


def get_research_status(mission_id: str) -> dict:
    if not enabled():
        return {"status": "error", "error": "Scientist research system is currently disabled."}
    mid = (mission_id or "").strip()
    if not mid:
        return {"status": "error", "error": "Provide a mission_id."}

    code, data, err = _http_request("GET", f"/api/missions/{urllib.parse.quote(mid)}/status")
    if err or code != 200:
        return {
            "status": "error",
            "error": f"Could not retrieve status for mission {mid}: {err or f'status {code}'}",
        }

    st = data.get("status", "UNKNOWN")
    phase = data.get("phase", "UNKNOWN")
    stage = data.get("stage", "UNKNOWN")
    iteration = data.get("iteration", 0)
    confidence = data.get("confidence")
    stop_reason = data.get("stop_reason")
    conf_str = f"{float(confidence):.2f}" if confidence is not None else "N/A"

    summary = (
        f"Mission {mid} is currently {st} (Phase: {phase}, Stage: {stage}, Iteration: {iteration}). "
        f"Bayesian confidence: {conf_str}."
    )
    if stop_reason:
        summary += f" Stop reason: {stop_reason}."

    return {
        "status": "success",
        "mission_id": mid,
        "data": data,
        "output": summary,
    }


def get_research_verdict(mission_id: str) -> dict:
    if not enabled():
        return {"status": "error", "error": "Scientist research system is currently disabled."}
    mid = (mission_id or "").strip()
    if not mid:
        return {"status": "error", "error": "Provide a mission_id."}

    code, data, err = _http_request("GET", f"/api/missions/{urllib.parse.quote(mid)}/verdict")
    if err or code != 200:
        return {
            "status": "error",
            "error": f"Could not retrieve verdict for mission {mid}: {err or f'status {code}'}",
        }

    label = data.get("label", "NO_VERDICT")
    confidence = data.get("confidence", 0.0)
    statement = data.get("statement", "No statement synthesized yet.")

    summary = (
        f"Scientific verdict for mission {mid}: {label} (confidence: {float(confidence):.2f}). "
        f"{statement}"
    )
    return {
        "status": "success",
        "mission_id": mid,
        "verdict_label": label,
        "confidence": confidence,
        "statement": statement,
        "output": summary,
    }


def get_research_report(mission_id: str, format: str = "markdown") -> dict:
    if not enabled():
        return {"status": "error", "error": "Scientist research system is currently disabled."}
    mid = (mission_id or "").strip()
    if not mid:
        return {"status": "error", "error": "Provide a mission_id."}

    code, data, err = _http_request("GET", f"/api/missions/{urllib.parse.quote(mid)}/report")
    if err or code != 200:
        return {
            "status": "error",
            "error": f"Could not retrieve report for mission {mid}: {err or f'status {code}'}",
        }

    body = data.get("body", "")
    conf = _get_config()
    dashboard_url = f"{conf['web_url']}/#/missions/{mid}"

    if len(body) > 2500:
        # Keep executive summary & verdict, add link to full dashboard
        lines = body.splitlines()
        trimmed = []
        char_count = 0
        for line in lines:
            trimmed.append(line)
            char_count += len(line) + 1
            if char_count > 2000 and line.startswith("#"):
                break
        truncated_body = "\n".join(trimmed).strip()
        summary = (
            f"{truncated_body}\n\n"
            f"[... Full comprehensive scientific report and raw artifact data available on the Scientist Dashboard: {dashboard_url} ...]"
        )
    else:
        summary = body or f"Report generated. View full interactive details at {dashboard_url}."

    return {
        "status": "success",
        "mission_id": mid,
        "format": format,
        "report_length": len(body),
        "dashboard_url": dashboard_url,
        "output": summary,
    }


# ---------------- Plugin Lifecycle & Dispatch ----------------

def init(**deps: Any) -> None:
    """Invoked by Layla during startup (_cap_init)."""
    with _lock:
        _D.update(deps)
    print("[scientist] layla_scientist plugin initialized", flush=True)


def turn_hint(message: str) -> Optional[str]:
    """Provides a subtle context cue if the conversation touches on scientific investigation."""
    if not enabled():
        return None
    msg = (message or "").lower()
    m = re.search(r"\b(sci-[a-f0-9]+)\b", msg, re.IGNORECASE)
    if m:
        return f"User mentions scientific mission {m.group(1).upper()}. You can check its status, verdict, or report."
    if any(k in msg for k in ("investigate", "scientific research", "hypothesis testing", "scientific verdict")):
        return "You have executive authority over Scientist OS (start_scientific_research, get_research_status, get_research_verdict, get_research_report)."
    return None


def call(name: str, args: Optional[dict] = None) -> dict:
    """Executes a Scientist OS tool call invoked by the conversational LLM.
    Never raises an uncaught exception.
    """
    args = args or {}
    try:
        if not enabled():
            return {"status": "error", "error": "Scientific research capabilities are currently switched off."}
        if name == "start_scientific_research":
            return start_scientific_research(args.get("question", ""), args.get("depth", "STANDARD"))
        if name == "get_research_status":
            return get_research_status(args.get("mission_id", ""))
        if name == "get_research_verdict":
            return get_research_verdict(args.get("mission_id", ""))
        if name == "get_research_report":
            return get_research_report(args.get("mission_id", ""), args.get("format", "markdown"))
        return {"status": "error", "error": f"Unknown scientific research tool: {name}"}
    except Exception as exc:
        return {"status": "error", "error": f"Error running {name}: {type(exc).__name__}: {exc}"}
