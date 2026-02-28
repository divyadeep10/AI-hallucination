# External Retrieval Layer

When **no evidence is found** from internal (knowledge-base) retrieval, the pipeline can run a **second retrieval layer** using web search (Playwright), then re-verify claims with the same NLI pipeline and mark evidence as external. You can turn this on or off with **`EXTERNAL_RETRIEVAL_ENABLED`** in `.env`.

## Flow

1. **Verification** runs as usual (internal evidence → NLI → Verification rows).
2. **External retrieval agent** runs next (only if `EXTERNAL_RETRIEVAL_ENABLED` is true):
   - Counts internal evidence (Evidence rows with `is_external=False` for this workflow’s claims).
   - If **any internal evidence exists**, it does nothing.
   - If **no internal evidence** was found:
     - Runs web search (Google) via Playwright with the workflow’s `user_query`.
     - Scrapes the **top 3** result pages (configurable).
     - Extracts and chunks page text.
     - For each claim, selects relevant chunks and runs the same `verify_claim_with_evidence` NLI.
     - Stores new **Evidence** rows with `is_external=True` and **Verification** rows for the new evidence.
3. **Critic** and **Refiner** then run as before (they see both internal and external evidence).

## Layout

- **`backend/app/external_retrieval/`**
  - **`config.py`** – env-based settings (EXTERNAL_RETRIEVAL_ENABLED, delays, timeouts, UA, viewport).
  - **`playwright_search.py`** – browser launch, Google search, URL collection, page scrape (human-like behavior).
  - **`scraper.py`** – HTML → main text extraction (strip script/style, normalize).
  - **`chunker.py`** – chunk scraped text for NLI (same idea as internal KB).
  - **`pipeline.py`** – `run_external_pipeline(query)` → list of `{snippet, source_url, is_external=True}`.
- **`backend/app/agents/external_retrieval.py`** – agent that checks `EXTERNAL_RETRIEVAL_ENABLED`, then “no internal evidence”; runs pipeline and stores external evidence and verifications.

## Playwright: Reducing Blocking

- **Random delays** between actions (`PLAYWRIGHT_DELAY_MIN` / `PLAYWRIGHT_DELAY_MAX`).
- **Typing delay** per character (`PLAYWRIGHT_TYPE_DELAY_MS`).
- **Realistic User-Agent** and viewport (e.g. Chrome on Windows).
- **Launch args**: `--disable-blink-features=AutomationControlled`, `--no-sandbox`, etc.
- **Single session**: one browser for search + scraping top N pages; short, linear flow.
- **Locale/timezone** set (e.g. `en-US`, `America/New_York`).

Optional: for stricter environments, consider proxy rotation or `playwright-stealth`; the current setup aims to look like a normal user without extra infra.

## Configuration (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `EXTERNAL_RETRIEVAL_ENABLED` | `true` | Set to `false` to disable external search entirely; when `true`, Playwright runs only when no internal evidence was found. |
| `EXTERNAL_TOP_N_PAGES` | `3` | Number of result pages to scrape. |
| `EXTERNAL_SEARCH_BASE_URL` | `https://www.google.com` | Search engine base URL. |
| `PLAYWRIGHT_HEADLESS` | `true` | Run browser headless. |
| `PLAYWRIGHT_TIMEOUT_MS` | `30000` | Page load timeout. |
| `PLAYWRIGHT_DELAY_MIN` / `PLAYWRIGHT_DELAY_MAX` | `2.0` / `5.0` | Min/max delay (seconds) between actions. |
| `PLAYWRIGHT_TYPE_DELAY_MS` | `80` | Delay per character when typing the query. |

## Setup

After installing Python deps (including `playwright`), install the browser:

```bash
playwright install chromium
```

Run migrations so the `evidence.is_external` column exists (migration `0010_add_evidence_is_external`).

## API / UI

- Evidence API responses include **`is_external`** (boolean).
- Frontend shows an **“External”** badge for evidence with `is_external === true`.
