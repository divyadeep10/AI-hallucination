# Wikipedia and Wikidata Retrieval

The RetrieverAgent gathers evidence from three sources **before** verification runs:

1. **Internal knowledge base** — hybrid retrieval (BM25 + embeddings) over `knowledge_chunks`.
2. **Wikipedia** — short textual explanations via the public [MediaWiki API](https://en.wikipedia.org/w/api.php) (search + intro extract). No API key, no Playwright.
3. **Wikidata** — structured facts via public [Wikidata APIs](https://www.wikidata.org/wiki/Wikidata:Data_access):
   - `wbsearchentities` to find entity by claim text
   - `Special:EntityData/<QID>.json` for entity claims
   - `wbgetentities` to resolve labels for readable snippets

All three are combined per claim, sorted by `retrieval_score`, and capped at 10 evidence items per claim. Verification (NLI/LLM) then runs once on this combined set.

## Configuration

| Variable | Default | Description |
|----------|---------|--------------|
| `WIKIPEDIA_RETRIEVAL_ENABLED` | `true` | Set to `false` to skip Wikipedia retrieval. |
| `WIKIDATA_RETRIEVAL_ENABLED` | `true` | Set to `false` to skip Wikidata retrieval. |

No API keys are required for Wikipedia or Wikidata; both use public HTTP endpoints.

## Evidence source field

Stored evidence includes a `source` value for UI display:

- `internal` — from the knowledge base
- `wikipedia` — from Wikipedia API
- `wikidata` — from Wikidata API
- `external` — from the optional Playwright layer (second retrieval, after verification)

The frontend shows a source badge (Internal, Wikipedia, Wikidata, External) next to each evidence snippet.

## Modules

- **Backend**: `app/retrieval_wikipedia.py`, `app/retrieval_wikidata.py`
- **Agent**: `app/agents/retriever.py` (orchestrates all three and stores with `source`)
