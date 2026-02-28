"""Quick diagnostic: check if Playwright can launch a browser."""
from playwright.sync_api import sync_playwright
import time

print("Testing Playwright browser launch...")
start = time.time()

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        print(f"✓ Browser launched in {time.time() - start:.1f}s")
        page = browser.new_page()
        page.goto("https://www.google.com", timeout=15000)
        print(f"✓ Loaded Google in {time.time() - start:.1f}s")
        title = page.title()
        print(f"✓ Page title: {title}")
        browser.close()
        print(f"✓ Total time: {time.time() - start:.1f}s")
        print("\n[SUCCESS] Playwright is working!")
except Exception as e:
    print(f"\n[ERROR] {e}")
    import traceback
    traceback.print_exc()
    print("\nTo fix: playwright install chromium")
