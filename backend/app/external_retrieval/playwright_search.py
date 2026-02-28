"""
Web search via Playwright with human-like behavior to reduce blocking.
Uses real browser, random delays, realistic UA/viewport, and typed input.
"""
import time
from typing import Optional

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from . import config as _config
from .scraper import _human_delay, extract_text_from_page


# Google selectors (may need updates if Google changes DOM)
GOOGLE_SEARCH_INPUT = 'textarea[name="q"], input[name="q"]'
GOOGLE_RESULT_LINKS = 'div#search a[href^="http"]:not([href*="google.com"])'


def _random_delay() -> None:
    import random
    time.sleep(random.uniform(_config.PLAYWRIGHT_DELAY_MIN, _config.PLAYWRIGHT_DELAY_MAX))


def _get_search_url() -> str:
    base = _config.SEARCH_BASE_URL.rstrip("/")
    if "google." in base:
        return f"{base}/search"
    return base


def run_search_and_scrape(
    query: str,
    top_n: int | None = None,
) -> list[tuple[str, str]]:
    """
    Run a web search, scrape top N result pages, return list of (url, full_text).
    Uses human-like delays and browser settings to reduce blocking.
    """
    top_n = top_n or _config.EXTERNAL_TOP_N_PAGES
    query = (query or "").strip()
    if not query:
        return []

    results: list[tuple[str, str]] = []
    timeout = _config.PLAYWRIGHT_TIMEOUT_MS

    with sync_playwright() as p:
        # Optional proxy (e.g. for IP rotation) from env
        proxy = None
        if _config.EXTERNAL_PLAYWRIGHT_PROXY:
            proxy = {"server": _config.EXTERNAL_PLAYWRIGHT_PROXY}
        browser = p.chromium.launch(
            headless=_config.PLAYWRIGHT_HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )
        context = browser.new_context(
            proxy=proxy,
            viewport={"width": _config.PLAYWRIGHT_VIEWPORT_WIDTH, "height": _config.PLAYWRIGHT_VIEWPORT_HEIGHT},
            user_agent=_config.PLAYWRIGHT_USER_AGENT,
            locale="en-US",
            timezone_id="America/New_York",
            ignore_https_errors=True,
        )
        # Reduce automation signals
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
        page = context.new_page()
        page.set_default_timeout(timeout)

        try:
            # Initial delay so the session doesn't look like an instant bot
            _random_delay()
            search_url = _get_search_url()
            if "google." in search_url:
                page.goto("https://www.google.com/", wait_until="domcontentloaded", timeout=timeout)
                _random_delay()
                # Type query slowly
                try:
                    page.click(GOOGLE_SEARCH_INPUT, timeout=8000)
                except PlaywrightTimeout:
                    # Fallback: focus and type
                    page.locator(GOOGLE_SEARCH_INPUT).first.focus()
                _random_delay()
                page.keyboard.type(query, delay=_config.PLAYWRIGHT_TYPE_DELAY_MS)
                _random_delay()
                page.keyboard.press("Enter")
                page.wait_for_load_state("domcontentloaded", timeout=timeout)
                _random_delay()
                page.wait_for_load_state("networkidle", timeout=timeout)
                _random_delay()

                # Collect result links (skip Google URLs)
                links: list[str] = []
                for a in page.locator(GOOGLE_RESULT_LINKS).all():
                    href = a.get_attribute("href")
                    if href and href.startswith("http") and "google.com" not in href:
                        links.append(href)
                        if len(links) >= top_n:
                            break

                # Scrape each result page
                seen = set()
                for url in links[:top_n]:
                    if url in seen:
                        continue
                    seen.add(url)
                    try:
                        _random_delay()
                        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                        _random_delay()
                        page.wait_for_load_state("networkidle", timeout=min(15000, timeout))
                        raw = page.content()
                        text = extract_text_from_page(raw, url)
                        if text and len(text.strip()) > 100:
                            results.append((url, text.strip()))
                    except Exception:
                        continue
            else:
                # Generic: just go to base URL and try to find a search box (simplified)
                page.goto(search_url, wait_until="domcontentloaded", timeout=timeout)
                _random_delay()
                # No generic search; return empty if not Google
                pass

        finally:
            context.close()
            browser.close()

    return results
