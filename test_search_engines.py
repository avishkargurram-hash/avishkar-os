import os
from playwright.sync_api import sync_playwright

os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/opt/scientist/browsers"

def test_engines():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = b.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        page = ctx.new_page()

        # 1. DuckDuckGo Lite / HTML
        page.goto("https://lite.duckduckgo.com/lite/", wait_until="domcontentloaded")
        page.fill("input[name='q']", "quantum computing")
        page.press("input[name='q']", "Enter")
        page.wait_for_timeout(2000)
        print("DDG Lite title:", page.title())
        links = page.query_selector_all(".result-link")
        print("DDG Lite result-links count:", len(links))

        # 2. Bing
        page.goto("https://www.bing.com/search?q=quantum+computing", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        print("Bing title:", page.title())
        bing_links = page.query_selector_all("li.b_algo h2 a")
        print("Bing results count:", len(bing_links))
        if bing_links:
            print("First Bing link:", bing_links[0].inner_text(), bing_links[0].get_attribute("href"))

        b.close()

if __name__ == "__main__":
    test_engines()
