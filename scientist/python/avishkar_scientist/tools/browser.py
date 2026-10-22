"""Headless Browser Action Worker for Avishkar OS (Pillar 2: Browser-Use).

Runs headless Chromium on tv-mum-01 to perform full autonomous web navigation,
bypassing bot-blockers, rendering dynamic JavaScript, executing interactive clicks/inputs,
and returning structured, sanitized markdown and metadata to Layla's executive brain.
"""

from __future__ import annotations

import base64
import html
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urljoin, urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

logger = logging.getLogger(__name__)

# Default browser path on tv-mum-01
DEFAULT_BROWSER_PATH = "/opt/scientist/browsers"
if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ and os.path.isdir(DEFAULT_BROWSER_PATH):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = DEFAULT_BROWSER_PATH

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _clean_html_to_markdown(html_content: str) -> str:
    """Strips noisy scripts, styles, navigations, and converts essential content to readable text."""
    if not html_content:
        return ""

    # Remove script and style tags
    clean = re.sub(r"<(script|style|svg|noscript)[^>]*>.*?</\1>", " ", html_content, flags=re.DOTALL | re.IGNORECASE)
    # Remove header, footer, nav tags to avoid boilerplate clutter
    clean = re.sub(r"<(header|footer|nav)[^>]*>.*?</\1>", " ", clean, flags=re.DOTALL | re.IGNORECASE)
    # Convert headings to markdown
    clean = re.sub(r"<h[1-2][^>]*>(.*?)</h[1-2]>", r"\n\n## \1\n\n", clean, flags=re.IGNORECASE | re.DOTALL)
    clean = re.sub(r"<h[3-6][^>]*>(.*?)</h[3-6]>", r"\n\n### \1\n\n", clean, flags=re.IGNORECASE | re.DOTALL)
    # Convert paragraphs and list items
    clean = re.sub(r"<p[^>]*>(.*?)</p>", r"\n\1\n", clean, flags=re.IGNORECASE | re.DOTALL)
    clean = re.sub(r"<li[^>]*>(.*?)</li>", r"\n- \1", clean, flags=re.IGNORECASE | re.DOTALL)
    # Convert links
    clean = re.sub(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', r"[\2](\1)", clean, flags=re.IGNORECASE | re.DOTALL)
    # Remove remaining HTML tags
    clean = re.sub(r"<[^>]+>", " ", clean)
    # Unescape HTML entities
    clean = html.unescape(clean)
    # Normalize excessive newlines and whitespace
    clean = re.sub(r"\n\s*\n\s*\n+", "\n\n", clean)
    clean = re.sub(r"[ \t]+", " ", clean)
    return clean.strip()


def browse_page(
    url: str,
    timeout_s: float = 30.0,
    wait_until: str = "domcontentloaded",
    capture_screenshot: bool = False,
    max_chars: int = 4000,
) -> Dict[str, Any]:
    """Navigates to a URL, evaluates dynamic JavaScript, and extracts title, content, and links."""
    t0 = time.perf_counter()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 800},
                ignore_https_errors=True,
            )
            page = context.new_page()

            # Navigate
            response = page.goto(url, wait_until=wait_until, timeout=int(timeout_s * 1000))
            page_status = response.status if response else 200

            # Brief pause for dynamic hydration
            page.wait_for_timeout(1000)

            title = page.title()
            final_url = page.url

            # Extract links
            raw_links = page.eval_on_selector_all(
                "a[href]",
                "elements => elements.map(e => ({ text: e.innerText.trim(), href: e.href }))"
            )
            filtered_links = []
            seen = set()
            for lnk in raw_links:
                href = lnk.get("href", "")
                text = lnk.get("text", "")
                if href and href.startswith("http") and href not in seen and text:
                    seen.add(href)
                    filtered_links.append({"text": text[:60], "href": href})
                if len(filtered_links) >= 12:
                    break

            # Extract content
            html_content = page.content()
            markdown = _clean_html_to_markdown(html_content)
            if len(markdown) > max_chars:
                markdown = markdown[:max_chars] + f"\n\n[... content truncated to {max_chars} chars ...]"

            screenshot_b64 = None
            if capture_screenshot:
                raw_ss = page.screenshot(type="jpeg", quality=60)
                screenshot_b64 = base64.b64encode(raw_ss).decode("utf-8")

            browser.close()
            elapsed_ms = (time.perf_counter() - t0) * 1000

            return {
                "status": "success",
                "url": final_url,
                "title": title,
                "http_status": page_status,
                "content": markdown,
                "links": filtered_links,
                "screenshot_b64": screenshot_b64,
                "latency_ms": round(elapsed_ms, 2),
            }
    except PlaywrightTimeoutError:
        return {
            "status": "timeout",
            "url": url,
            "error": f"Page load timed out after {timeout_s}s",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
        }
    except Exception as exc:
        return {
            "status": "error",
            "url": url,
            "error": f"{type(exc).__name__}: {exc}",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
        }


def search_web_headless(query: str, max_results: int = 5) -> Dict[str, Any]:
    """Executes a headless search via Bing without external search API keys."""
    t0 = time.perf_counter()
    search_url = f"https://www.bing.com/search?q={quote_plus(query)}"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(user_agent=USER_AGENT)
            page = context.new_page()

            page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(1500)
            results = []

            # Extract search snippets
            elements = page.query_selector_all("li.b_algo")
            for el in elements:
                h2 = el.query_selector("h2 a")
                p_text = el.query_selector(".b_caption p") or el.query_selector("p")
                if h2:
                    title = h2.inner_text().strip()
                    href = h2.get_attribute("href") or ""
                    snippet = p_text.inner_text().strip() if p_text else ""
                    if title and href.startswith("http"):
                        results.append({"title": title, "url": href, "snippet": snippet})
                if len(results) >= max_results:
                    break

            browser.close()
            elapsed_ms = (time.perf_counter() - t0) * 1000

            # Formulate human readable output
            lines = [f"{i+1}. [{r['title']}]({r['url']})\n   {r['snippet']}" for i, r in enumerate(results)]
            output_str = f"Search Results for '{query}' ({len(results)} found):\n\n" + "\n\n".join(lines) if lines else f"No results found for '{query}'."

            return {
                "status": "success",
                "query": query,
                "count": len(results),
                "results": results,
                "output": output_str,
                "latency_ms": round(elapsed_ms, 2),
            }
    except Exception as exc:
        return {
            "status": "error",
            "query": query,
            "error": f"Search failed: {type(exc).__name__}: {exc}",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
        }


def execute_browser_actions(steps: List[Dict[str, Any]], start_url: Optional[str] = None, timeout_s: float = 35.0) -> Dict[str, Any]:
    """Executes a sequential list of UI actions (goto, click, fill, press, wait, screenshot, extract)."""
    t0 = time.perf_counter()
    action_log = []
    extracted_data = {}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 800})
            page = context.new_page()

            if start_url:
                page.goto(start_url, wait_until="domcontentloaded", timeout=15000)
                action_log.append(f"Navigated to {start_url}")

            for i, step in enumerate(steps):
                act = step.get("action", "").lower().strip()
                selector = step.get("selector")
                val = step.get("value") or step.get("text")

                if act == "goto":
                    page.goto(val or step.get("url"), wait_until="domcontentloaded", timeout=15000)
                    action_log.append(f"Step {i+1}: goto {val}")
                elif act == "click" and selector:
                    page.click(selector, timeout=5000)
                    action_log.append(f"Step {i+1}: clicked '{selector}'")
                elif act in ("type", "fill") and selector and val is not None:
                    page.fill(selector, str(val), timeout=5000)
                    action_log.append(f"Step {i+1}: filled '{selector}'")
                elif act == "press":
                    key = step.get("key", "Enter")
                    page.keyboard.press(key)
                    action_log.append(f"Step {i+1}: pressed '{key}'")
                elif act == "wait":
                    ms = int(step.get("ms", 1000))
                    page.wait_for_timeout(ms)
                    action_log.append(f"Step {i+1}: waited {ms}ms")
                elif act == "extract":
                    target_sel = selector or "body"
                    txt = page.inner_text(target_sel)
                    var_name = step.get("name", f"extract_{i+1}")
                    extracted_data[var_name] = txt[:2000]
                    action_log.append(f"Step {i+1}: extracted '{target_sel}'")

            final_title = page.title()
            final_url = page.url
            browser.close()
            elapsed_ms = (time.perf_counter() - t0) * 1000

            return {
                "status": "success",
                "final_url": final_url,
                "title": final_title,
                "action_log": action_log,
                "extracted": extracted_data,
                "latency_ms": round(elapsed_ms, 2),
            }
    except Exception as exc:
        return {
            "status": "error",
            "action_log": action_log,
            "error": f"Action sequence failed: {type(exc).__name__}: {exc}",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
        }
