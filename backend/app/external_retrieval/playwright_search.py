"""
Multi-source web search: Wikipedia, Google, DuckDuckGo fallbacks.
When Google returns 0 links, try Wikipedia first (most reliable), then DDG.
"""
import time
from typing import Optional

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from . import config as _config
from .scraper import extract_text_from_page


def _random_delay() -> None:
    import random
    time.sleep(random.uniform(_config.PLAYWRIGHT_DELAY_MIN, _config.PLAYWRIGHT_DELAY_MAX))


def _scrape_url_with_retry(page, url: str, timeout: int, max_retries: int = 2) -> Optional[str]:
    """Scrape one URL with retries; wait for body then extract text."""
    for attempt in range(max_retries):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
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
                print(f"[EXTERNAL_RETRIEVAL] Scrape failed {url[:50]}...: {e}")
                return None
            time.sleep(1.0 * (attempt + 1))
    return None


def _search_wikipedia(query: str, page, timeout: int, top_n: int) -> list[tuple[str, str]]:
    """
    Search Wikipedia and return top N article texts.
    Most reliable source with clean text and no blocking.
    """
    print(f"[EXTERNAL_RETRIEVAL] Trying Wikipedia for '{query[:50]}...'")
    results = []
    
    try:
        # Wikipedia search
        search_url = f"https://en.wikipedia.org/w/index.php?search={query.replace(' ', '+')}"
        page.goto(search_url, wait_until="domcontentloaded", timeout=timeout)
        _random_delay()
        
        # Check if we got a direct article (redirect) or search results
        current_url = page.url
        
        if "/wiki/" in current_url and "/wiki/Special:" not in current_url:
            # Direct article - scrape it
            text = _scrape_url_with_retry(page, current_url, timeout)
            if text:
                results.append((current_url, text))
                print(f"[EXTERNAL_RETRIEVAL] Wikipedia: got article {current_url[:60]}")
        else:
            # Search results page - get top articles
            try:
                page.wait_for_selector(".mw-search-results", timeout=8000)
            except Exception:
                pass
            
            # Get result links
            links = []
            for a in page.locator(".mw-search-results a[href^='/wiki/']").all()[:top_n]:
                href = a.get_attribute("href")
                if href and "/wiki/" in href and "/Special:" not in href:
                    full_url = f"https://en.wikipedia.org{href}"
                    if full_url not in links:
                        links.append(full_url)
            
            print(f"[EXTERNAL_RETRIEVAL] Wikipedia: found {len(links)} article links")
            
            # Scrape each article
            for url in links[:top_n]:
                _random_delay()
                text = _scrape_url_with_retry(page, url, timeout)
                if text:
                    results.append((url, text))
                    print(f"[EXTERNAL_RETRIEVAL] Wikipedia: scraped {len(text)} chars from {url[:60]}")
    
    except Exception as e:
        print(f"[EXTERNAL_RETRIEVAL] Wikipedia search failed: {e}")
    
    return results


def _search_google(query: str, page, timeout: int, top_n: int) -> list[tuple[str, str]]:
    """Search Google and scrape top N results."""
    print(f"[EXTERNAL_RETRIEVAL] Trying Google for '{query[:50]}...'")
    results = []
    
    try:
        page.goto("https://www.google.com/", wait_until="domcontentloaded", timeout=timeout)
        _random_delay()
        
        # Dismiss consent
        for consent_text in ["Accept all", "I agree", "Accept All", "Agree"]:
            try:
                btn = page.get_by_role("button", name=consent_text)
                btn.wait_for(state="visible", timeout=2000)
                btn.click(timeout=2000)
                _random_delay()
                break
            except Exception:
                continue
        
        # Search
        search_input = 'textarea[name="q"], input[name="q"]'
        try:
            page.wait_for_selector(search_input, state="visible", timeout=timeout)
            page.locator(search_input).first.click(timeout=5000)
        except Exception:
            page.locator(search_input).first.focus()
        
        _random_delay()
        page.keyboard.type(query, delay=_config.PLAYWRIGHT_TYPE_DELAY_MS)
        _random_delay()
        page.keyboard.press("Enter")
        
        try:
            page.wait_for_selector("div#search", state="visible", timeout=timeout)
        except Exception:
            pass
        try:
            page.wait_for_load_state("domcontentloaded", timeout=timeout)
        except Exception:
            pass
        _random_delay()
        
        # Get links with multiple selector attempts
        links = []
        js_get_href = "(el) => el.href"
        
        for selector in [
            "div#search div.g a[href^='http']",
            "div#rso a[href^='http']",
            "div#search a[href^='http']",
            "a[href^='http']"
        ]:
            if links:
                break
            try:
                loc = page.locator(selector)
                loc.first.wait_for(state="visible", timeout=5000)
                raw_hrefs = loc.evaluate_all(js_get_href)
                if isinstance(raw_hrefs, list):
                    for h in raw_hrefs:
                        h_str = str(h)
                        if h_str.startswith("http") and "google.com" not in h_str and "gstatic" not in h_str:
                            base = h_str.split("?")[0]
                            if base not in links:
                                links.append(h_str)
                                if len(links) >= top_n:
                                    break
            except Exception:
                continue
        
        # Retry once if empty
        if not links:
            _random_delay()
            for selector in ["div#search a[href^='http']", "a[href^='http']"]:
                try:
                    for a in page.locator(selector).all()[:top_n * 2]:
                        href = a.get_attribute("href")
                        if href and href.startswith("http") and "google.com" not in href and "gstatic" not in href:
                            base = href.split("?")[0]
                            if base not in links:
                                links.append(href)
                                if len(links) >= top_n:
                                    break
                    if links:
                        break
                except Exception:
                    continue
        
        print(f"[EXTERNAL_RETRIEVAL] Google: found {len(links)} result links")
        
        # Scrape each
        for url in links[:top_n]:
            _random_delay()
            text = _scrape_url_with_retry(page, url, timeout)
            if text:
                results.append((url, text))
                print(f"[EXTERNAL_RETRIEVAL] Google: scraped {len(text)} chars from {url[:60]}")
    
    except Exception as e:
        print(f"[EXTERNAL_RETRIEVAL] Google search failed: {e}")
    
    return results


def run_search_and_scrape(
    query: str,
    top_n: int | None = None,
) -> list[tuple[str, str]]:
    """
    Multi-source search: tries Wikipedia first (most reliable), then Google.
    Returns list of (url, text) tuples.
    """
    top_n = top_n or _config.EXTERNAL_TOP_N_PAGES
    query = (query or "").strip()
    if not query:
        return []
    
    results: list[tuple[str, str]] = []
    timeout = _config.PLAYWRIGHT_TIMEOUT_MS
    sources = [s.strip().lower() for s in _config.SEARCH_SOURCES.split(",")]
    
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
            
            if _config.PLAYWRIGHT_BLOCK_RESOURCES:
                try:
                    def handle_route(route):
                        if route.request.resource_type in ("image", "stylesheet", "font", "media"):
                            route.abort()
                        else:
                            route.continue_()
                    page.route("**/*", handle_route)
                except Exception:
                    pass
            
            try:
                for source in sources:
                    if source == "wikipedia":
                        results = _search_wikipedia(query, page, timeout, top_n)
                    elif source == "google":
                        results = _search_google(query, page, timeout, top_n)
                    
                    if results:
                        print(f"[EXTERNAL_RETRIEVAL] Success with {source}: {len(results)} pages")
                        break
            
            finally:
                context.close()
                browser.close()
    
    except Exception as e:
        print(f"[EXTERNAL_RETRIEVAL] Playwright error: {e}")
        import traceback
        traceback.print_exc()
        return []
    
    print(f"[EXTERNAL_RETRIEVAL] Total: returning {len(results)} scraped pages")
    return results
