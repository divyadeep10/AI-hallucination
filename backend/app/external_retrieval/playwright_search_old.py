"""
Web search via Playwright – follows working scraping patterns:
explicit waits for selectors, evaluate_all for extraction, retries, optional resource blocking.
"""
import time
from typing import Optional

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from . import config as _config
from .scraper import extract_text_from_page


# Stable selectors (semantic / structure; avoid fragile class chains)
GOOGLE_SEARCH_INPUT = 'textarea[name="q"], input[name="q"]'
# Results container – wait for this before extracting links
GOOGLE_RESULTS_CONTAINER = "div#search"
# Result blocks (Google uses div.g for each result)
GOOGLE_RESULT_LINKS_IN_CONTAINER = "div#search a[href^='http']"
# Fallback: any non-Google link in main content
GOOGLE_RESULT_LINKS_FALLBACK = "a[href^='http']"


def _random_delay() -> None:
    import random
    time.sleep(random.uniform(_config.PLAYWRIGHT_DELAY_MIN, _config.PLAYWRIGHT_DELAY_MAX))


def _get_search_url() -> str:
    base = _config.SEARCH_BASE_URL.rstrip("/")
    if "google." in base:
        return f"{base}/search"
    return base


def _setup_route_block_resources(page) -> None:
    """Block images, stylesheets, fonts to speed up and reduce fingerprint (optional)."""
    try:
        def handle_route(route):
            rtype = route.request.resource_type
            if rtype in ("image", "stylesheet", "font", "media"):
                route.abort()
            else:
                route.continue_()

        page.route("**/*", handle_route)
    except Exception:
        pass


def _dismiss_consent(page, timeout: int = 5000) -> None:
    """Dismiss cookie/consent banner if present (e.g. EU)."""
    for consent_text in ["Accept all", "I agree", "Accept All", "Accept"]:
        try:
            btn = page.get_by_role("button", name=consent_text)
            btn.wait_for(state="visible", timeout=2000)
            btn.click(timeout=2000)
            _random_delay()
            return
        except Exception:
            continue


def _collect_result_links_with_evaluate(page, top_n: int, timeout: int) -> list[str]:
    """
    Wait for results container, then use evaluate_all to get hrefs (one per element).
    Dedupe and filter Google in Python.
    """
    try:
        page.wait_for_selector(GOOGLE_RESULTS_CONTAINER, state="visible", timeout=timeout)
    except Exception:
        pass

    # evaluate_all: JS runs per element, returns array of results. (el) => el.href
    js_get_href = "(el) => el.href"

    for selector in [GOOGLE_RESULT_LINKS_IN_CONTAINER, GOOGLE_RESULT_LINKS_FALLBACK]:
        try:
            loc = page.locator(selector)
            loc.first.wait_for(state="visible", timeout=5000)
            raw_hrefs = loc.evaluate_all(js_get_href)
            if not isinstance(raw_hrefs, list):
                continue
            seen: set[str] = set()
            links: list[str] = []
            for h in raw_hrefs:
                if not h or not str(h).startswith("http"):
                    continue
                if "google.com" in str(h) or "gstatic.com" in str(h):
                    continue
                base = str(h).split("?")[0].rstrip("/")
                if base in seen:
                    continue
                seen.add(base)
                links.append(str(h))
                if len(links) >= top_n:
                    return links
            if links:
                return links
        except Exception:
            continue

    # Fallback: iterate in Python
    seen = set()
    links = []
    for selector in [GOOGLE_RESULT_LINKS_IN_CONTAINER, GOOGLE_RESULT_LINKS_FALLBACK]:
        if len(links) >= top_n:
            break
        try:
            for node in page.locator(selector).all():
                href = node.get_attribute("href")
                if not href or not href.startswith("http") or "google.com" in href or "gstatic.com" in href:
                    continue
                base = href.split("?")[0].rstrip("/")
                if base in seen:
                    continue
                seen.add(base)
                links.append(href)
                if len(links) >= top_n:
                    break
        except Exception:
            continue
    return links[:top_n]


def _scrape_url_with_retry(page, url: str, timeout: int, max_retries: int = 2) -> Optional[str]:
    """Scrape one URL with retries; wait for body then extract text."""
    for attempt in range(max_retries):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            # Explicit wait for content (avoid relying only on load state)
            page.wait_for_selector("body", state="attached", timeout=10000)
            try:
                page.wait_for_load_state("networkidle", timeout=min(12000, timeout))
            except Exception:
                pass
            raw = page.content()
            text = extract_text_from_page(raw, url)
            if text and len(text.strip()) > 80:
                return text.strip()
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"[EXTERNAL_RETRIEVAL] Playwright: scrape failed {url[:50]}...: {e}")
                return None
            time.sleep(1.0 * (attempt + 1))
    return None


def run_search_and_scrape(
    query: str,
    top_n: int | None = None,
) -> list[tuple[str, str]]:
    """
    Run web search, scrape top N result pages. Uses:
    - Explicit waits (wait_for_selector) instead of only fixed delays
    - evaluate_all to extract links from DOM
    - Retries for search and per-URL scrape
    - Optional resource blocking
    """
    top_n = top_n or _config.EXTERNAL_TOP_N_PAGES
    query = (query or "").strip()
    if not query:
        return []

    results: list[tuple[str, str]] = []
    timeout = _config.PLAYWRIGHT_TIMEOUT_MS
    search_timeout = min(20000, timeout)

    try:
        with sync_playwright() as p:
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
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
            page = context.new_page()
            page.set_default_timeout(timeout)

            # Optional: block heavy resources to speed up and reduce detection
            if _config.PLAYWRIGHT_BLOCK_RESOURCES:
                _setup_route_block_resources(page)

            try:
                _random_delay()
                search_url = _get_search_url()
                if "google." not in search_url:
                    return []

                print("[EXTERNAL_RETRIEVAL] Playwright: opening Google...")
                page.goto("https://www.google.com/", wait_until="domcontentloaded", timeout=timeout)
                # Explicit wait for search input (stable selector)
                page.wait_for_selector(GOOGLE_SEARCH_INPUT, state="visible", timeout=search_timeout)
                _random_delay()
                _dismiss_consent(page, timeout=5000)

                # Focus and type query
                page.locator(GOOGLE_SEARCH_INPUT).first.click(timeout=5000)
                _random_delay()
                page.keyboard.type(query, delay=_config.PLAYWRIGHT_TYPE_DELAY_MS)
                _random_delay()
                page.keyboard.press("Enter")

                # Wait for results container (explicit wait instead of fixed delay)
                try:
                    page.wait_for_selector(GOOGLE_RESULTS_CONTAINER, state="visible", timeout=search_timeout)
                except Exception:
                    pass
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=search_timeout)
                except Exception:
                    pass
                _random_delay()

                links = _collect_result_links_with_evaluate(page, top_n, timeout=10000)
                if not links:
                    # Retry once: wait a bit and try again (handles slow/finicky load)
                    _random_delay()
                    links = _collect_result_links_with_evaluate(page, top_n, timeout=10000)
                print(f"[EXTERNAL_RETRIEVAL] Playwright: found {len(links)} result links for query '{query[:50]}...'")
                if not links:
                    return []

                seen = set()
                for url in links:
                    if url in seen:
                        continue
                    seen.add(url)
                    _random_delay()
                    text = _scrape_url_with_retry(page, url, timeout=min(20000, timeout), max_retries=2)
                    if text:
                        results.append((url, text))
                        print(f"[EXTERNAL_RETRIEVAL] Playwright: scraped {len(text)} chars from {url[:60]}...")

            finally:
                context.close()
                browser.close()

    except Exception as e:
        print(f"[EXTERNAL_RETRIEVAL] Playwright error: {e}")
        import traceback
        traceback.print_exc()
        return []

    print(f"[EXTERNAL_RETRIEVAL] Playwright: returning {len(results)} scraped pages")
    return results
