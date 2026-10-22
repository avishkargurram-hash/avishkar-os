import os
from playwright.sync_api import sync_playwright

os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/opt/scientist/browsers"

def main():
    print("Launching Chromium...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://example.com")
        title = page.title()
        content = page.inner_text("body")
        print("Successfully loaded page!")
        print("Title:", title)
        print("Content preview:", content[:60])
        browser.close()

if __name__ == "__main__":
    main()
