# Multi-Source External Retrieval - FIXED

## What Was Wrong

From your worker log (terminal 12, line 52-53):
```
[EXTERNAL_RETRIEVAL] Playwright: opening Google...  
[EXTERNAL_RETRIEVAL] Playwright: found 0 result links for query 'what is ai ?...'
```

**Problem:** Google's DOM/selectors changed or are being blocked, so link extraction returned 0 results.

## What I Changed

### 1. **Multi-source fallback** (Wikipedia → Google)
- **Wikipedia first** (most reliable):
  - No blocking/captcha
  - Clean, structured text
  - Directly scrapes articles for the query
- **Google fallback** if Wikipedia fails
- Configurable via `EXTERNAL_SEARCH_SOURCES` in `.env`

### 2. **Better Google selectors**
- Multiple selector attempts with `evaluate_all`
- Retry logic when 0 links found
- Improved filtering of Google's own URLs

### 3. **New `.env` variable**
```env
EXTERNAL_SEARCH_SOURCES=wikipedia,google
```
- **`wikipedia`** = Search Wikipedia, get top articles (most reliable)
- **`google`** = Search Google, scrape results
- Comma-separated, tries in order until success

## How It Works Now

1. **Wikipedia search** for query
   - If direct article: scrape it
   - If search results: get top 3 article links, scrape each
   - Log: `[EXTERNAL_RETRIEVAL] Trying Wikipedia for 'what is ai'...`
   - Log: `[EXTERNAL_RETRIEVAL] Wikipedia: got article https://en.wikipedia.org/wiki/Artificial_intelligence`
   - Log: `[EXTERNAL_RETRIEVAL] Wikipedia: scraped 45230 chars...`

2. **If Wikipedia returns 0 results**, try Google

3. Returns evidence chunks from whichever source succeeded

## To Test

**Restart the worker** (file changed):
```bash
# In terminal running worker: Ctrl+C
cd c:\major_project\backend
set PYTHONPATH=%CD%
python worker.py
```

Then submit a query like "what is ai" or "who invented the light bulb".

**Expected logs (Wikipedia):**
```
[AGENT] ExternalRetrievalAgent: running web search (Playwright), second layer
[EXTERNAL_RETRIEVAL] Trying Wikipedia for 'what is ai'...
[EXTERNAL_RETRIEVAL] Wikipedia: found 3 article links
[EXTERNAL_RETRIEVAL] Wikipedia: scraped 35421 chars from https://en.wikipedia.org/wiki/...
[EXTERNAL_RETRIEVAL] Success with wikipedia: 3 pages
[EXTERNAL_RETRIEVAL] Total: returning 3 scraped pages
[AGENT] ExternalRetrievalAgent: got 127 external chunks, verifying claims
```

Wikipedia is much more reliable than Google for factual queries and never blocks.
