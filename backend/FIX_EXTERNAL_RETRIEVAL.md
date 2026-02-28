# EXTERNAL RETRIEVAL NOT WORKING - FIX

## Problem Found

The worker (terminal 4) shows:
```
[AGENT] ExternalRetrievalAgent: internal evidence found (15 rows), skipping web search
```

This means:
1. External retrieval agent **IS** running (good!)
2. But it's using **OLD CODE** that checks for internal evidence before running Playwright
3. The **NEW CODE** (already written) always runs Playwright when enabled

## Solution: RESTART THE WORKER

**Steps:**

### 1. Stop the current worker
In the terminal running `python worker.py` (likely terminal 4):
- Press `Ctrl+C` to stop it

### 2. Restart the worker
```bash
cd c:\major_project\backend
set PYTHONPATH=%CD%
python worker.py
```

### 3. Test with a new query
- Go to the frontend (http://localhost:5173)
- Submit a new query (e.g. "Who invented the light bulb?")
- Watch the worker terminal for these new logs:

**You should now see:**
```
[AGENT] ExternalRetrievalAgent: running web search (Playwright), second layer
[EXTERNAL_RETRIEVAL] Playwright: opening Google...
[EXTERNAL_RETRIEVAL] Playwright: found N result links...
[EXTERNAL_RETRIEVAL] Playwright: scraped X chars from https://...
```

### 4. Check the UI
After ~10-30 seconds (Playwright takes time), refresh the claims view.
You should see:
- Claims with SUPPORTED/CONTRADICTED instead of NO_EVIDENCE
- Evidence with "External" badges

---

## What Changed in the Code

**Old code (what your worker is running):**
```python
internal_evidence_count = db.query(Evidence).filter(...).count()
if internal_evidence_count > 0:
    print("internal evidence found, skipping web search")
    return
```

**New code (what we wrote):**
```python
# Always run Playwright (permanent second layer)
print("running web search (Playwright), second layer")
external_items = run_external_pipeline(query)
```

The worker must be restarted to load the new code.
