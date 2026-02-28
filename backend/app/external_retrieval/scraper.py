"""
Scrape a single URL with Playwright and extract main text content.
Uses simple body-text extraction; avoids script/style and keeps paragraphs.
"""
import re
import time
from typing import Optional

from . import config as _config


def _human_delay() -> None:
    """Apply a random delay between actions to mimic human behavior."""
    import random
    t = random.uniform(_config.PLAYWRIGHT_DELAY_MIN, _config.PLAYWRIGHT_DELAY_MAX)
    time.sleep(t)


def extract_text_from_page(html: str, url: str = "") -> str:
    """
    Extract main text from HTML without a browser.
    Removes script, style, nav, footer; normalizes whitespace.
    Used after we have page content from Playwright.
    """
    if not html or not html.strip():
        return ""
    # Remove script and style
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    # Strip tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode common entities
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text[:100000]  # Cap length


def scrape_url(
    url: str,
    *,
    page,  # playwright.sync_api.Page
    timeout_ms: int | None = None,
) -> Optional[str]:
    """
    Navigate to URL with Playwright page, wait for load, extract text.
    Returns extracted text or None on failure.
    """
    timeout_ms = timeout_ms or _config.PLAYWRIGHT_TIMEOUT_MS
    try:
        _human_delay()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        _human_delay()
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
        content = page.content()
        return extract_text_from_page(content, url)
    except Exception:
        return None
