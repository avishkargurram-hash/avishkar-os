"""Layla God's Eye View (GEV) Plugin -- Real-time planetary intelligence and 3D globe console.

Connects Layla's brain as an MCP client to God's Eye View running on tv-mum-01.
Provides 29+ live data tools:
  - Live aircraft tracking (civilian + military)
  - Live vessel tracking via AIS
  - Satellites overhead & passes (ISS, etc.)
  - Real-time earthquakes (USGS)
  - Active wildfires (NASA FIRMS)
  - Traffic flow (TomTom) & CCTV camera snapshots
  - Submarine cables, datacenters, dams, military installations
  - Weather maps, cyclones, terrain elevation, situation briefs

Integrates with Layla's voice/spoken output (via `summary`) and her face UI / screens
(via SSE `open_panel: "globe"` event with embed-mode URL).

Kill switch: GODSEYE=0 in .env. Never raises into the caller.
"""

import json
import os
import re
import threading
import time
import urllib.request
import urllib.error

# Configuration with environment defaults
DEFAULT_GEV_URL = "http://103.168.22.202:4173/mcp"
DEFAULT_GEV_KEY = "d53a5c29fd677344dcc67a8e8cf1854dd7a9a9af5ed64e52abb2a641eb61da48"
DEFAULT_PUBLIC_URL = "http://103.168.22.202:4173"
TIMEOUT_SECS = 15

_D = {}  # memory, push, execute_tool
_lock = threading.Lock()

# Load catalog from bundled gev_catalog.json if present
CATALOG_PATH = os.path.join(os.path.dirname(__file__), "gev_catalog.json")


def enabled():
    """Kill switch: GODSEYE=0 in /opt/layla/.env turns God's Eye View off."""
    return os.environ.get("GODSEYE", "1") != "0"


def _get_config():
    return {
        "url": os.environ.get("GODSEYE_URL", DEFAULT_GEV_URL),
        "key": os.environ.get("GODSEYE_KEY", DEFAULT_GEV_KEY),
        "public_url": os.environ.get("GODSEYE_PUBLIC_URL", DEFAULT_PUBLIC_URL).rstrip("/"),
    }


def _load_raw_catalog():
    if os.path.exists(CATALOG_PATH):
        try:
            with open(CATALOG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


# Build initial tool definitions from catalog
_raw = _load_raw_catalog()
TOOLS = []
NAMES = set()

for t in _raw:
    tname = t.get("name", "")
    # panel_request is strictly internal to the MCP app panel runtime, not for conversational LLM
    if not tname or tname == "panel_request":
        continue
    NAMES.add(tname)
    desc = t.get("description", "") or t.get("title", "")
    schema = t.get("inputSchema", {"type": "object", "properties": {}})
    TOOLS.append({
        "type": "function",
        "function": {
            "name": tname,
            "description": desc,
            "parameters": schema,
        }
    })

# Rich keywords for Layla's category router
KEYWORDS = (
    "gods eye", "god's eye", "globe", "satellite", "satellites", "iss", "orbit",
    "flight", "flights", "aircraft", "plane", "planes", "military flight",
    "ship", "ships", "vessel", "vessels", "boat", "maritime", "ais",
    "earthquake", "earthquakes", "quake", "tremor", "seismic",
    "fire", "fires", "wildfire", "wildfires", "firms",
    "cyclone", "cyclones", "hurricane", "typhoon", "storm",
    "cctv", "traffic camera", "camera snapshot", "traffic flow",
    "alpr", "license plate",
    "submarine cable", "undersea cable", "datacenter", "dam", "infrastructure",
    "military base", "military installation", "weather radar", "weather map",
    "situation brief", "terrain height", "elevation"
)


def init(**deps):
    """Called during Layla startup with shared services (memory, push, etc.)."""
    _D.update(deps)


def _rpc_call(method, params=None):
    cfg = _get_config()
    payload = {
        "jsonrpc": "2.0",
        "id": int(time.time() * 1000),
        "method": method,
    }
    if params is not None:
        payload["params"] = params

    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "layla/1.0",
    }
    if cfg["key"]:
        headers["X-GEV-Key"] = cfg["key"]

    req = urllib.request.Request(cfg["url"], data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECS) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _format_view_url(raw_url, public_base):
    """Normalize view URL to point to public GEV address with embed=1."""
    if not raw_url:
        return ""
    # Replace localhost/127.0.0.1 with public GEV server address
    url = re.sub(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?", public_base, raw_url)
    # Ensure embed=1 is present for iframe/panel presentation
    if "#" in url:
        base, frag = url.split("#", 1)
        if "embed=1" not in base:
            sep = "&" if "?" in base else "?"
            url = f"{base}{sep}embed=1#{frag}"
    elif "embed=1" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}embed=1"
    return url


def call(name, args):
    """Execute a God's Eye View tool call. Never raises into the caller."""
    if not enabled():
        return {"status": "error", "error": "God's Eye View capability is disabled (GODSEYE=0)"}

    args = args or {}
    try:
        cfg = _get_config()
        resp = _rpc_call("tools/call", {"name": name, "arguments": args})

        if "error" in resp:
            err = resp["error"]
            msg = err.get("message", "Unknown MCP error") if isinstance(err, dict) else str(err)
            return {"status": "error", "error": f"GEV error: {msg}"}

        result = resp.get("result", {})
        if result.get("isError"):
            err_content = result.get("content", [{}])
            msg = err_content[0].get("text", "Tool execution failed") if err_content else "Tool execution failed"
            return {"status": "error", "error": f"GEV tool error: {msg}"}

        # Extract text summary for Layla's spoken reply
        summary = ""
        content_items = result.get("content", [])
        for item in content_items:
            if isinstance(item, dict) and item.get("type") == "text":
                summary = item.get("text", "").strip()
                if summary:
                    break

        struct = result.get("structuredContent") or {}
        if not summary and struct:
            # Fallback if summary was in structuredContent
            summary = struct.get("summary") or ""

        if not summary:
            summary = f"Retrieved data for {name}."

        # Check for interactive 3D globe view
        view = struct.get("view") if isinstance(struct, dict) else None
        view_url = ""
        if isinstance(view, dict) and view.get("url"):
            view_url = _format_view_url(view.get("url"), cfg["public_url"])
            view["url"] = view_url

        # Push SSE event to Layla face UI if a globe view exists
        if view_url and "push" in _D and callable(_D["push"]):
            try:
                _D["push"]({
                    "type": "open_panel",
                    "panel": "globe",
                    "url": view_url,
                    "title": name.replace("_", " ").title(),
                    "tool": name,
                })
            except Exception:
                pass  # SSE push is best-effort; never fail the tool call

        return {
            "status": "success",
            "output": summary,
            "data": struct,
            "view_url": view_url,
        }

    except urllib.error.HTTPError as e:
        return {"status": "error", "error": f"GEV service HTTP {e.code}: {e.reason}"}
    except urllib.error.URLError as e:
        return {"status": "error", "error": f"GEV service unreachable: {e.reason}"}
    except Exception as e:
        return {"status": "error", "error": f"GEV call exception: {type(e).__name__}: {e}"}
