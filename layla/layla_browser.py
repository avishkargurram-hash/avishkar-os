"""Layla Browser Plugin -- Headless Autonomous Browser Worker (Pillar 2).

Enables Layla's executive brain to browse live web pages, execute headless search,
and interact with dynamic DOM elements via the Playwright worker running on tv-mum-01.

Tools:
  - browse_web(url, capture_screenshot=False)
  - search_web(query, max_results=5)
  - interact_web(steps, start_url=None)

Kill switch: BROWSER_USE=0 in /opt/layla/.env. Never raises into the caller.
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
TIMEOUT_SECS = 45

_D: Dict[str, Any] = {}
_lock = threading.Lock()


def enabled() -> bool:
    """Kill switch: BROWSER_USE=0 in /opt/layla/.env turns Browser integration off."""
    return os.environ.get("BROWSER_USE", "1") != "0"


def _get_config() -> dict[str, str]:
    return {
        "api_url": os.environ.get("SCIENTIST_API_URL", DEFAULT_API_URL).rstrip("/"),
        "token": os.environ.get("SCIENTIST_API_TOKEN", DEFAULT_API_TOKEN).strip(),
    }


def _http_request(method: str, path: str, payload: Optional[dict] = None, timeout: int = TIMEOUT_SECS) -> tuple[int, Any, Optional[str]]:
    """Makes an authenticated HTTP request to the Scientist/Browser API service.
    Returns (status_code, parsed_json_or_text, error_message).
    Never raises exceptions.
    """
    conf = _get_config()
    url = f"{conf['api_url']}{path}"
    headers = {
        "Authorization": f"Bearer {conf['token']}",
        "User-Agent": "Layla-Brain/Browser-1.0",
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

def browse_web(url: str, capture_screenshot: bool = False) -> dict:
    """Navigate to a webpage using a headless Chromium browser on tv-mum-01,
    evaluate dynamic JavaScript, and extract clean text and links.
    """
    if not url:
        return {"status": "error", "error": "URL parameter is required."}

    code, resp, err = _http_request("POST", "/api/browser/browse", {
        "url": url,
        "capture_screenshot": capture_screenshot,
        "timeout_s": 30.0,
    }, timeout=35)

    if err or code != 200 or not isinstance(resp, dict):
        return {"status": "error", "error": err or f"HTTP {code} from browser service"}

    if resp.get("status") != "success":
        return {"status": "error", "error": resp.get("error", "Unknown browser error")}

    title = resp.get("title", "Untitled")
    final_url = resp.get("url", url)
    content = resp.get("content", "")
    links = resp.get("links", [])
    latency_ms = resp.get("latency_ms", 0)

    summary = (
        f"Page Title: {title}\n"
        f"URL: {final_url}\n"
        f"Execution Time: {latency_ms}ms\n\n"
        f"Extracted Content:\n{content}"
    )

    return {
        "status": "success",
        "title": title,
        "url": final_url,
        "content": content,
        "links": links,
        "screenshot_b64": resp.get("screenshot_b64"),
        "latency_ms": latency_ms,
        "output": summary,
    }


def search_web(query: str, max_results: int = 5) -> dict:
    """Search the web using a headless browser on tv-mum-01 without needing API keys,
    extracting clean search result titles, snippets, and URLs.
    """
    if not query:
        return {"status": "error", "error": "Query parameter is required."}

    code, resp, err = _http_request("POST", "/api/browser/search", {
        "query": query,
        "max_results": max(1, min(10, int(max_results))),
    }, timeout=25)

    if err or code != 200 or not isinstance(resp, dict):
        return {"status": "error", "error": err or f"HTTP {code} from browser service"}

    if resp.get("status") != "success":
        return {"status": "error", "error": resp.get("error", "Unknown search error")}

    results = resp.get("results", [])
    count = resp.get("count", len(results))
    output_text = resp.get("output", "")
    latency_ms = resp.get("latency_ms", 0)

    return {
        "status": "success",
        "query": query,
        "count": count,
        "results": results,
        "latency_ms": latency_ms,
        "output": output_text,
    }


def interact_web(steps: List[Dict[str, Any]], start_url: Optional[str] = None) -> dict:
    """Execute multi-step browser UI interactions (click, type, press, wait, extract) on tv-mum-01."""
    if not steps or not isinstance(steps, list):
        return {"status": "error", "error": "steps must be a non-empty list of action dicts."}

    code, resp, err = _http_request("POST", "/api/browser/interact", {
        "steps": steps,
        "start_url": start_url,
        "timeout_s": 35.0,
    }, timeout=40)

    if err or code != 200 or not isinstance(resp, dict):
        return {"status": "error", "error": err or f"HTTP {code} from browser service"}

    if resp.get("status") != "success":
        return {"status": "error", "error": resp.get("error", "Unknown interaction error")}

    action_log = resp.get("action_log", [])
    extracted = resp.get("extracted", {})
    latency_ms = resp.get("latency_ms", 0)

    summary = (
        f"Completed {len(action_log)} UI interaction steps in {latency_ms}ms.\n"
        f"Actions:\n" + "\n".join(f"- {act}" for act in action_log)
    )
    if extracted:
        summary += "\n\nExtracted Data:\n" + "\n".join(f"{k}: {v}" for k, v in extracted.items())

    return {
        "status": "success",
        "final_url": resp.get("final_url"),
        "title": resp.get("title"),
        "action_log": action_log,
        "extracted": extracted,
        "latency_ms": latency_ms,
        "output": summary,
    }


# ---------------- Schema & Tool Definitions ----------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "browse_web",
            "description": "Navigate to a webpage using a headless Chromium browser on tv-mum-01, bypass bot-blockers, evaluate dynamic JavaScript, and extract clean markdown text and links.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The full HTTP/HTTPS URL or domain to browse."},
                    "capture_screenshot": {"type": "boolean", "description": "Whether to capture a base64 JPEG screenshot."},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the live web using headless browser on tv-mum-01 to retrieve current real-world information, news, documentation, or links.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search keywords or query."},
                    "max_results": {"type": "integer", "description": "Maximum number of search results to retrieve (default 5)."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "interact_web",
            "description": "Execute multi-step browser interactions (goto, click, fill/type, press, wait, extract) on tv-mum-01 to automate interactive web flows.",
            "parameters": {
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Sequence of step dictionaries, e.g. [{'action': 'goto', 'url': '...'}, {'action': 'fill', 'selector': '#q', 'value': 'test'}, {'action': 'press', 'key': 'Enter'}, {'action': 'extract', 'selector': '.result'}]",
                    },
                    "start_url": {"type": "string", "description": "Optional initial URL to open before executing steps."},
                },
                "required": ["steps"],
            },
        },
    },
]

NAMES = ["browse_web", "search_web", "interact_web"]

KEYWORDS = [
    "browse", "browser", "website", "webpage", "web page", "open website",
    "scrape", "search web", "check website", "web link", "url", "bing search",
    "look up online", "internet search", "google", "web"
]


# ---------------- Plugin Lifecycle & Dispatch ----------------

def init(**deps: Any) -> None:
    with _lock:
        _D.update(deps)
    print("[browser] layla_browser plugin initialized", flush=True)


def turn_hint(message: str) -> Optional[str]:
    """Provides situational awareness hint if query involves browsing or web search."""
    if not enabled():
        return None
    msg = (message or "").lower()
    if any(k in msg for k in ("search web", "browse", "website", "web page", "look up online", "url")):
        return "You have autonomous headless browser capabilities (browse_web, search_web, interact_web) on tv-mum-01."
    return None


def call(name: str, args: Optional[dict] = None) -> dict:
    args = args or {}
    try:
        if not enabled():
            return {"status": "error", "error": "Browser capability is disabled."}
        if name == "browse_web":
            return browse_web(args.get("url", ""), args.get("capture_screenshot", False))
        if name == "search_web":
            return search_web(args.get("query", ""), int(args.get("max_results", 5)))
        if name == "interact_web":
            return interact_web(args.get("steps", []), args.get("start_url"))
        return {"status": "error", "error": f"Unknown browser tool: {name}"}
    except Exception as exc:
        return {"status": "error", "error": f"Error running {name}: {type(exc).__name__}: {exc}"}
