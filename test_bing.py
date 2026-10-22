import os
from playwright.sync_api import sync_playwright

os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/opt/scientist/browsers"

def test_bing():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = b.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        page = ctx.new_page()

        page.goto("https://www.bing.com/search?q=quantum+computing", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(2000)
        print("Bing title:", page.title())
        results = []
        for el in page.query_selector_all("li.b_algo"):
            h2 = el.query_selector("h2 a")
            p_text = el.query_selector(".b_caption p") or el.query_selector("p")
            if h2:
                title = h2.inner_text().strip()
                href = h2.get_attribute("href")
                snippet = p_text.inner_text().strip() if p_text else ""
                results.append({"title": title, "url": href, "snippet": snippet})
        print(f"Bing results found: {len(results)}")
        for r in results[:3]:
            print(f" - {r['title']} -> {r['url']}")
        b.close()

if __name__ == "__main__":
    test_bing()
