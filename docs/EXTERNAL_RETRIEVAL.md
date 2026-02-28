# External Retrieval Layer

**Permanent second retrieval layer:** internal (knowledge-base) retrieval runs first, then Playwright (web search) always runs when enabled. Both layers’ evidence are **combined**; Critic and Refiner see internal + external evidence. Turn the second layer on or off with **`EXTERNAL_RETRIEVAL_ENABLED`** in `.env`.

## Flow

1. **Internal retrieval** (RetrieverAgent): hybrid search over KB → Evidence rows (`is_external=False`).
2. **Verification** runs: NLI over internal evidence → Verification rows.
3. **External retrieval agent** runs next (only if `EXTERNAL_RETRIEVAL_ENABLED` is true):
   - Always runs web search (Google) via Playwright with the workflow’s `user_query`.
   - Scrapes the **top 3** result pages (configurable).
   - Extracts and chunks page text.
   - For each claim, selects relevant chunks and runs the same `verify_claim_with_evidence` NLI.
   - Stores new **Evidence** rows with `is_external=True` and **Verification** rows for the new evidence.
4. **Critic** and **Refiner** see **both** internal and external evidence.

No check for “no internal evidence”; Playwright is a fixed second layer when enabled.

## Layout

- **`backend/app/external_retrieval/`**
  - **`config.py`** – env-based settings (EXTERNAL_RETRIEVAL_ENABLED, delays, timeouts, UA, viewport).
  - **`playwright_search.py`** – browser launch, Google search, URL collection, page scrape (human-like behavior).
  - **`scraper.py`** – HTML → main text extraction (strip script/style, normalize).
  - **`chunker.py`** – chunk scraped text for NLI (same idea as internal KB).
  - **`pipeline.py`** – `run_external_pipeline(query)` → list of `{snippet, source_url, is_external=True}`.
- **`backend/app/agents/external_retrieval.py`** – agent that runs when `EXTERNAL_RETRIEVAL_ENABLED` is true; runs pipeline and stores external evidence and verifications (combined with internal).

## Playwright: Scraping Best Practices

- **Explicit waits**: `wait_for_selector(..., state="visible")` for search input and results container instead of only fixed delays.
- **Stable selectors**: `textarea[name="q"]`, `div#search`, `div#search a[href^='http']` (semantic/structure).
- **Extract with evaluate_all**: `locator.evaluate_all("(el) => el.href")` to get hrefs from DOM in one shot; dedupe/filter in Python.
- **Retries**: One retry for link collection if first run returns 0 links; per-URL scrape retries (2 attempts).
- **Optional resource blocking**: Set `PLAYWRIGHT_BLOCK_RESOURCES=true` to block images/stylesheets/fonts (faster, less fingerprint).
- **Consent banner**: Clicks "Accept all" / "I agree" if visible before interacting with search.
- **Human-like**: Random delays, typing delay, real UA/viewport, `--disable-blink-features=AutomationControlled`.

## Configuration (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `EXTERNAL_RETRIEVAL_ENABLED` | `true` | Set to `false` to disable the second layer; when `true`, Playwright always runs and evidence is combined with internal. |
| `EXTERNAL_TOP_N_PAGES` | `3` | Number of result pages to scrape. |
| `EXTERNAL_SEARCH_BASE_URL` | `https://www.google.com` | Search engine base URL. |
| `PLAYWRIGHT_HEADLESS` | `true` | Run browser headless. |
| `PLAYWRIGHT_TIMEOUT_MS` | `30000` | Page load timeout. |
| `PLAYWRIGHT_DELAY_MIN` / `PLAYWRIGHT_DELAY_MAX` | `2.0` / `5.0` | Min/max delay (seconds) between actions. |
| `PLAYWRIGHT_TYPE_DELAY_MS` | `80` | Delay per character when typing the query. |
| `PLAYWRIGHT_BLOCK_RESOURCES` | `false` | Set to `true` to block images/stylesheets/fonts (faster, less fingerprint). |

## Setup

After installing Python deps (including `playwright`), install the browser:

```bash
playwright install chromium
```

Run migrations so the `evidence.is_external` column exists (migration `0010_add_evidence_is_external`).

## API / UI

- Evidence API responses include **`is_external`** (boolean).
- Frontend shows an **“External”** badge for evidence with `is_external === true`.
