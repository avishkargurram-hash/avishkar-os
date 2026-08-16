"""Real BrowserExecutor tests. Genuinely launches headless Chromium
via Playwright and drives it against `data:` URLs -- no network
dependency, no live site, and (unlike GUI/mouse/keyboard control)
headless browsing never touches this machine's real visible desktop,
so it's safe and appropriate to run for real, automatically.
"""

import unittest

from avishkar_layla.executors.browser_executor import BrowserExecutor
from avishkar_layla.executors.errors import BrowserActionError, UnknownActionError

_PAGE = (
    "data:text/html,<html><body>"
    "<h1 id='title'>Hello Avishkar</h1>"
    "<input id='box' />"
    "<button id='btn' onclick=\"document.getElementById('title').innerText='Clicked'\">Click</button>"
    "</body></html>"
)


class TestBrowserExecutorReal(unittest.TestCase):
    def setUp(self):
        self.executor = BrowserExecutor(headless=True)

    def tearDown(self):
        self.executor.close()

    def test_navigate_and_get_text(self):
        result = self.executor("navigate", {"url": _PAGE})
        self.assertIn("data:", result["url"])

        text = self.executor("get_text", {"selector": "#title"})
        self.assertEqual(text["text"], "Hello Avishkar")

    def test_type_into_a_real_input(self):
        self.executor("navigate", {"url": _PAGE})
        result = self.executor("type", {"selector": "#box", "text": "avishkar layla"})
        self.assertEqual(result["filled"], "#box")

    def test_click_actually_changes_real_page_state(self):
        self.executor("navigate", {"url": _PAGE})
        self.executor("click", {"selector": "#btn"})
        text = self.executor("get_text", {"selector": "#title"})
        self.assertEqual(text["text"], "Clicked")

    def test_screenshot_produces_real_png_bytes(self):
        self.executor("navigate", {"url": _PAGE})
        result = self.executor("screenshot", {})
        self.assertGreater(result["size"], 0)
        self.assertTrue(result["png_bytes"].startswith(b"\x89PNG"))

    def test_unknown_action_raises(self):
        with self.assertRaises(UnknownActionError):
            self.executor("teleport", {})

    def test_click_on_missing_selector_raises_browser_action_error(self):
        self.executor("navigate", {"url": _PAGE})
        with self.assertRaises(BrowserActionError):
            self.executor("click", {"selector": "#does-not-exist", "timeout_ms": 500})

    def test_close_is_idempotent(self):
        self.executor("navigate", {"url": _PAGE})
        self.executor("close", {})
        self.executor("close", {})  # must not raise

    def test_session_persists_across_calls(self):
        """navigate then click operate on the SAME real page -- one
        executor instance is one persistent browser session, per
        Directive D Part III's act-then-observe chain.
        """
        self.executor("navigate", {"url": _PAGE})
        before = self.executor("get_url", {})
        self.executor("click", {"selector": "#btn"})
        after = self.executor("get_url", {})
        self.assertEqual(before["url"], after["url"])


if __name__ == "__main__":
    unittest.main()
