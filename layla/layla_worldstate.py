"""Layla WorldState Plugin -- Persistent Digital Reality Graph (Pillar 7).

Provides Layla with durable awareness of all server nodes (Oracle Cloud, tv-mum-01,
Workstation PC), connected IoT hardware devices (bedroom fan, switchboard, mobile robot),
active multi-day background workflows, and scientific research missions.

Tools:
  - get_world_state(focus="all")
  - update_world_entity(entity_id, kind, name, state={}, metadata={})
  - manage_workflow(action="list", workflow_id=None, goal=None, status="ACTIVE", step_progress=0, total_steps=None, assigned_node="oracle")

Kill switch: WORLDSTATE=0 in /opt/layla/.env. Never raises into the caller.
"""

from __future__ import annotations

import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

# Configuration with environment defaults
DEFAULT_API_URL = "http://103.168.22.202:8095"
DEFAULT_API_TOKEN = ""
TIMEOUT_SECS = 15

_D: Dict[str, Any] = {}
_lock = threading.Lock()


def enabled() -> bool:
    """Kill switch: WORLDSTATE=0 in /opt/layla/.env turns WorldState integration off."""
    return os.environ.get("WORLDSTATE", "1") != "0"


def _get_config() -> dict[str, str]:
    return {
        "api_url": os.environ.get("SCIENTIST_API_URL", DEFAULT_API_URL).rstrip("/"),
        "token": os.environ.get("SCIENTIST_API_TOKEN", DEFAULT_API_TOKEN).strip(),
    }


def _http_request(method: str, path: str, payload: Optional[dict] = None) -> tuple[int, Any, Optional[str]]:
    """Makes an authenticated HTTP request to the Scientist/WorldState API service.
    Returns (status_code, parsed_json_or_text, error_message).
    Never raises exceptions.
    """
    conf = _get_config()
    url = f"{conf['api_url']}{path}"
    headers = {
        "Authorization": f"Bearer {conf['token']}",
        "User-Agent": "Layla-Brain/WorldState-1.0",
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


# ---------------- Tool Implementations ----------------

def get_world_state(focus: str = "all") -> dict:
    """Retrieve digital reality graph state (servers, devices, workflows, missions)."""
    if not enabled():
        return {"status": "error", "error": "WorldState capability is currently disabled (WORLDSTATE=0)."}

    focus = (focus or "all").lower().strip()
    code, data, err = _http_request("GET", "/api/world/summary")
    if err or code != 200 or not isinstance(data, dict):
        return {
            "status": "error",
            "error": f"Could not retrieve world state from backend: {err or f'status {code}'}",
        }

    narrative = data.get("narrative", "")
    servers = data.get("servers", [])
    devices = data.get("devices", [])
    workflows = data.get("active_workflows", [])
    missions = data.get("active_missions", [])

    if focus == "servers":
        lines = [f"- {s['name']}: {s.get('state', {}).get('role', 'Node')} (Status: {s.get('state', {}).get('status', 'UNKNOWN')})" for s in servers]
        output_str = f"Servers ({len(servers)} total):\n" + "\n".join(lines)
    elif focus == "devices":
        lines = [f"- {d['name']}: Status: {d.get('state', {}).get('status', 'UNKNOWN')}" for d in devices]
        output_str = f"IoT Devices ({len(devices)} total):\n" + "\n".join(lines)
    elif focus == "workflows":
        lines = [f"- [{w['id']}] {w['goal']} (Step {w.get('step_progress', 0)} on {w.get('assigned_node', 'oracle')})" for w in workflows]
        output_str = f"Active Workflows ({len(workflows)} total):\n" + ("\n".join(lines) if lines else "No active workflows.")
    elif focus == "missions":
        lines = [f"- [{m['id']}] {m['question']} (Status: {m.get('status')})" for m in missions]
        output_str = f"Research Missions ({len(missions)} total):\n" + ("\n".join(lines) if lines else "No research missions active.")
    else:
        output_str = narrative

    return {
        "status": "success",
        "focus": focus,
        "narrative": narrative,
        "servers": servers,
        "devices": devices,
        "active_workflows": workflows,
        "active_missions": missions,
        "output": output_str,
    }


def update_world_entity(entity_id: str, kind: str, name: str, state: Optional[dict] = None, metadata: Optional[dict] = None) -> dict:
    """Register or update an entity's live status in the digital reality graph."""
    if not enabled():
        return {"status": "error", "error": "WorldState capability is currently disabled."}
    if not entity_id or not entity_id.strip():
        return {"status": "error", "error": "entity_id is required."}

    payload = {
        "kind": (kind or "SERVICE").upper(),
        "name": name or entity_id,
        "state": state or {},
        "metadata": metadata or {},
    }
    code, data, err = _http_request("POST", f"/api/world/entities/{urllib.parse.quote(entity_id.strip())}", payload)
    if err or code != 200:
        return {
            "status": "error",
            "error": f"Failed to update entity '{entity_id}': {err or f'status {code}'}",
        }
    return {
        "status": "success",
        "entity_id": entity_id,
        "output": f"Entity '{entity_id}' state updated successfully.",
    }


def manage_workflow(action: str = "list", workflow_id: Optional[str] = None, goal: Optional[str] = None, status: str = "ACTIVE", step_progress: int = 0, total_steps: Optional[int] = None, assigned_node: str = "oracle") -> dict:
    """Inspect or update a persistent multi-day workflow across nodes."""
    if not enabled():
        return {"status": "error", "error": "WorldState capability is currently disabled."}

    action = (action or "list").lower().strip()
    if action == "list":
        code, data, err = _http_request("GET", f"/api/workflows?status={urllib.parse.quote(status)}")
        if err or code != 200:
            return {"status": "error", "error": f"Failed to list workflows: {err}"}
        lines = [f"- [{w['id']}] {w['goal']} (Status: {w.get('status')}, Node: {w.get('assigned_node')})" for w in (data or [])]
        out_str = f"Found {len(data or [])} workflows:\n" + ("\n".join(lines) if lines else "No workflows found.")
        return {"status": "success", "count": len(data or []), "workflows": data, "output": out_str}

    if not workflow_id or not workflow_id.strip():
        return {"status": "error", "error": "workflow_id is required for create/update actions."}

    payload = {
        "goal": goal or "General task",
        "status": status.upper(),
        "initiator": "layla",
        "assigned_node": assigned_node,
        "context": {},
        "step_progress": step_progress,
        "total_steps": total_steps,
    }
    code, data, err = _http_request("POST", f"/api/workflows/{urllib.parse.quote(workflow_id.strip())}", payload)
    if err or code != 200:
        return {"status": "error", "error": f"Failed to update workflow '{workflow_id}': {err}"}
    return {
        "status": "success",
        "workflow_id": workflow_id,
        "output": f"Workflow '{workflow_id}' updated to status {status.upper()} (Step {step_progress}).",
    }


# ---------------- OpenAI Function Tool Schemas ----------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_world_state",
            "description": "Inspect the persistent digital reality graph: all server nodes (Oracle, tv-mum-01, PC), connected IoT hardware (bedroom fan, switchboard, robot), active multi-day workflows, and scientific missions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "focus": {
                        "type": "string",
                        "enum": ["all", "servers", "devices", "workflows", "missions"],
                        "description": "Subset of world state to focus on (default 'all').",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_world_entity",
            "description": "Register or update an entity's status in the digital reality graph (e.g. server load, hardware state, or active service status).",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string", "description": "Unique entity ID (e.g. server.oracle, device.robot)."},
                    "kind": {"type": "string", "enum": ["SERVER", "DEVICE", "PROJECT", "AGENT", "SERVICE", "INFRA"], "description": "Entity category."},
                    "name": {"type": "string", "description": "Readable display name."},
                    "state": {"type": "object", "description": "Key-value map of live state attributes."},
                    "metadata": {"type": "object", "description": "Optional static metadata."},
                },
                "required": ["entity_id", "kind", "name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "manage_workflow",
            "description": "Inspect or advance persistent multi-day workflows across nodes (e.g. long research runs, background data sweeps).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["list", "create", "update"], "description": "Action to perform."},
                    "workflow_id": {"type": "string", "description": "Unique workflow ID."},
                    "goal": {"type": "string", "description": "Summary of the workflow goal."},
                    "status": {"type": "string", "enum": ["ACTIVE", "PAUSED", "COMPLETED", "FAILED"], "description": "Workflow status."},
                    "step_progress": {"type": "integer", "description": "Current step counter."},
                    "total_steps": {"type": "integer", "description": "Total steps expected if known."},
                    "assigned_node": {"type": "string", "description": "Target compute node (oracle, tv-mum-01, pc)."},
                },
                "required": [],
            },
        },
    },
]

NAMES = ["get_world_state", "update_world_entity", "manage_workflow"]

KEYWORDS = [
    "world state", "servers", "server", "nodes", "node", "infrastructure",
    "devices", "device", "ecosystem", "workflow", "workflows", "active workflow",
    "mumbai server", "oracle server", "pc status", "digital reality"
]


# ---------------- Plugin Lifecycle & Dispatch ----------------

def init(**deps: Any) -> None:
    with _lock:
        _D.update(deps)
    print("[worldstate] layla_worldstate plugin initialized", flush=True)


def turn_hint(message: str) -> Optional[str]:
    """Provides situational awareness hint if query involves servers or infrastructure."""
    if not enabled():
        return None
    msg = (message or "").lower()
    if any(k in msg for k in ("server", "servers", "infrastructure", "nodes", "ecosystem", "active workflow", "workflows")):
        return "You have persistent access to the ecosystem Digital Reality Graph (get_world_state, update_world_entity, manage_workflow)."
    return None


def call(name: str, args: Optional[dict] = None) -> dict:
    args = args or {}
    try:
        if not enabled():
            return {"status": "error", "error": "WorldState capability is disabled."}
        if name == "get_world_state":
            return get_world_state(args.get("focus", "all"))
        if name == "update_world_entity":
            return update_world_entity(
                args.get("entity_id", ""),
                args.get("kind", "SERVICE"),
                args.get("name", ""),
                args.get("state"),
                args.get("metadata"),
            )
        if name == "manage_workflow":
            return manage_workflow(
                args.get("action", "list"),
                args.get("workflow_id"),
                args.get("goal"),
                args.get("status", "ACTIVE"),
                int(args.get("step_progress", 0)),
                args.get("total_steps"),
                args.get("assigned_node", "oracle"),
            )
        return {"status": "error", "error": f"Unknown worldstate tool: {name}"}
    except Exception as exc:
        return {"status": "error", "error": f"Error running {name}: {type(exc).__name__}: {exc}"}
