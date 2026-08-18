"""Real browser automation executor for EMBODIMENT_BROWSER. See
CONTRACT.md SS34.

STATUS: REAL. Wraps the real `playwright.sync_api` -- genuinely
launches a Chromium instance (headless by default) and drives it.
Unlike screen/microphone capture, a HEADLESS browser session never
touches the real visible desktop or any physical device, so it is
safe to exercise for real, automatically, in the test suite (see
test_browser_executor.py -- real navigate/click/fill/get_text/
screenshot against `data:` URLs, no network dependency, no live site
involved).
"""

from __future__ import annotations

from typing import Any, Mapping

from .errors import BrowserActionError, UnknownActionError
from .ssrf_guard import unsafe_navigation_reason

_ACTIONS = ("navigate", "click", "type", "get_text", "get_url", "screenshot", "evaluate_text_content", "close")


class BrowserExecutor:
    """One instance = one persistent real browser session across
    calls, so `navigate` then `click` operate on the same real page --
    matching Directive D Part III's Observation -> Verification chain
    (act, then observe the result of that same page).
    """

    def __init__(self, *, headless: bool = True, default_timeout_ms: float = 15000) -> None:
        self._headless = headless
        self._default_timeout_ms = default_timeout_ms
        self._playwright = None
        self._browser = None
        self._page = None

    def _ensure_page(self):
        if self._page is None:
            try:
                from playwright.sync_api import sync_playwright
            except ImportError as exc:
                raise BrowserActionError("the 'playwright' package is not installed -- required for BrowserExecutor") from exc
            try:
                self._playwright = sync_playwright().start()
                self._browser = self._playwright.chromium.launch(headless=self._headless)
                self._page = self._browser.new_page()
                self._page.set_default_timeout(self._default_timeout_ms)
            except Exception as exc:
                self.close()
                raise BrowserActionError(f"failed to launch a real browser session: {exc}") from exc
        return self._page

    def __call__(self, action: str, parameters: Mapping[str, Any]) -> Any:
        if action not in _ACTIONS:
            raise UnknownActionError(f"BrowserExecutor has no action {action!r} -- expected one of {_ACTIONS}")
        if action == "close":
            self.close()
            return {"closed": True}

        page = self._ensure_page()
        try:
            if action == "navigate":
                # Real SSRF guard (Directive D Part XIII, ADR-0040): a
                # hard block, not merely a risk-classification nudge --
                # see ssrf_guard.py for why "navigate to a URL" reads
                # as harmless text even when the target is a cloud
                # metadata endpoint.
                unsafe_reason = unsafe_navigation_reason(parameters["url"])
                if unsafe_reason is not None:
                    raise BrowserActionError(f"navigation refused: {unsafe_reason}")
                timeout_ms = parameters.get("timeout_ms", self._default_timeout_ms)
                page.goto(parameters["url"], timeout=timeout_ms)
                return {"url": page.url, "title": page.title()}
            if action == "click":
                page.click(parameters["selector"], timeout=parameters.get("timeout_ms", self._default_timeout_ms))
                return {"clicked": parameters["selector"]}
            if action == "type":
                page.fill(parameters["selector"], parameters["text"])
                return {"filled": parameters["selector"], "text_length": len(parameters["text"])}
            if action == "get_text":
                return {"text": page.inner_text(parameters["selector"])}
            if action == "get_url":
                return {"url": page.url, "title": page.title()}
            if action == "evaluate_text_content":
                return {"text": page.text_content(parameters.get("selector", "body")) or ""}
            if action == "screenshot":
                png_bytes = page.screenshot(full_page=parameters.get("full_page", False))
                return {"png_bytes": png_bytes, "size": len(png_bytes)}
        except BrowserActionError:
            raise
        except Exception as exc:
            raise BrowserActionError(f"browser action {action!r} failed: {exc}") from exc

        raise UnknownActionError(f"BrowserExecutor has no handler wired for action {action!r}")  # pragma: no cover

    def close(self) -> None:
        try:
            if self._browser is not None:
                self._browser.close()
        finally:
            self._browser = None
            self._page = None
            if self._playwright is not None:
                try:
                    self._playwright.stop()
                finally:
                    self._playwright = None

    def __del__(self) -> None:  # pragma: no cover -- best-effort cleanup only
        try:
            self.close()
        except Exception:
            pass
