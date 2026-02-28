# Setup and Run Guide

This guide covers how to install dependencies, configure the environment, and run the Self-Correcting Multi-Agent AI system (Phases 0–9).

---

## 1. Prerequisites

- **Python 3.10+** (3.11 or 3.12 recommended)
- **Node.js 18+** and npm (for the frontend)
- **PostgreSQL 12+** (running locally or reachable URL)
- **Redis 6+** (for the background job queue)
- **Git** (to clone the repo)

Optional for full Docker deployment:

- **Docker** and **Docker Compose**

---

## 2. Clone and project layout

```bash
git clone <your-repo-url>
cd major_project
```

Key directories:

| Path | Purpose |
|------|--------|
| `backend/` | FastAPI app, agents, DB models, migrations |
| `frontend/` | React + Vite UI |
| `docs/` | Roadmap, this guide |
| `.env` | Your secrets (create from `.env.example`) |

---

## 3. Environment configuration

### 3.1 Create `.env`

From the project root:

```bash
cp .env.example .env
```

Edit `.env` and set at least:

- **`DATABASE_URL`** – PostgreSQL connection string, e.g.  
  `postgresql+psycopg2://USER:PASSWORD@HOST:5432/DATABASE`
- **`REDIS_URL`** – Redis URL, e.g. `redis://localhost:6379/0`
- **One LLM provider:**
  - **OpenAI**: set `OPENAI_API_KEY` (and optionally `OPENAI_API_BASE`, `OPENAI_MODEL`)
  - **Gemini**: set `GEMINI_API_KEY` (and optionally `GEMINI_API_BASE`, `GEMINI_MODEL`)

Optional:

- **`FRONTEND_ORIGIN`** – CORS origin for the frontend (default `http://localhost:5173`)
- **`BACKEND_PORT`** – Port for the API (default `8000`)

### 3.2 Switching LLM providers

- If **both** `OPENAI_API_KEY` and `GEMINI_API_KEY` are set, the app uses **OpenAI first**.
- To use only Gemini: set `GEMINI_API_KEY` and leave `OPENAI_API_KEY` empty.
- To use a different OpenAI-compatible API (e.g. Azure, local model): set `OPENAI_API_KEY` and `OPENAI_API_BASE` (and `OPENAI_MODEL` if needed).

Configuration is centralized in `backend/app/config.py`; env vars are documented in `.env.example`.

### 3.3 External retrieval (second retrieval layer)

When internal retrieval yields fewer than 40% supported claims, the pipeline can run a web search (Playwright) and re-verify. See **[docs/EXTERNAL_RETRIEVAL.md](EXTERNAL_RETRIEVAL.md)** for details. Optional env vars: `EXTERNAL_RETRIEVAL_ENABLED` (enable/disable; when true, runs only when no internal evidence), `EXTERNAL_TOP_N_PAGES`, `PLAYWRIGHT_*`, and optionally `EXTERNAL_PLAYWRIGHT_PROXY` for IP rotation. After installing Python deps, run `playwright install chromium`.

---

## 4. Run locally (without Docker)

### 4.1 PostgreSQL and Redis

Ensure PostgreSQL and Redis are running and reachable at the URLs you put in `.env`.

Examples:

- **PostgreSQL**: install locally or use a cloud instance; create a database and set `DATABASE_URL`.
- **Redis**: `redis-server` locally, or use a managed Redis.

### 4.2 Backend

From the project root:

```bash
# Install Python dependencies (recommended: use a virtualenv)
pip install -r requirements.txt

# Optional: for external retrieval (web search when internal evidence is low)
playwright install chromium

# Run migrations (from backend directory, with backend on PYTHONPATH)
cd backend
set PYTHONPATH=%CD%           # Windows
# export PYTHONPATH=$(pwd)    # Linux/macOS
alembic upgrade head
cd ..
```

Start the API:

```bash
cd backend
set PYTHONPATH=%CD%           # Windows
# export PYTHONPATH=$(pwd)    # Linux/macOS
uvicorn app.main:app --reload --port 8000
```

Leave this terminal open. The API will be at `http://localhost:8000`.

### 4.3 Start the RQ worker (required for full pipeline)

In a **second** terminal:

```bash
cd backend
set PYTHONPATH=%CD%           # Windows
# export PYTHONPATH=$(pwd)    # Linux/macOS
python worker.py
```

Leave this running so that workflow jobs (planner → generator → … → refiner) are processed.

### 4.4 Frontend

In a **third** terminal:

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** in the browser. The UI will call the backend at `http://localhost:8000` by default (override with `VITE_API_BASE_URL` if needed).

---

## 5. Run with Docker Compose

From the project root, with Docker and Docker Compose installed:

### 5.1 Configure `.env`

Ensure `.env` exists (from `.env.example`) and contains at least:

- **One of** `OPENAI_API_KEY` or `GEMINI_API_KEY`
- Optionally override: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` (defaults are in `docker-compose.yml`)
- For the frontend build (calling API from the host browser):  
  `VITE_API_BASE_URL=http://localhost:8000`  
  so the SPA talks to the backend on the host’s port 8000.

### 5.2 Build and start

```bash
docker compose up --build
```

This starts:

- **PostgreSQL** (port 5432)
- **Redis** (port 6379)
- **Backend API** (port 8000; runs migrations on startup)
- **Worker** (RQ worker for the pipeline)
- **Frontend** (port 5173 → container 80)

Open:

- Frontend: **http://localhost:5173**
- API docs: **http://localhost:8000/docs**

### 5.3 Stop

```bash
docker compose down
```

Add `-v` to remove the Postgres volume: `docker compose down -v`.

---

## 6. Evaluation script (Phase 8)

To run baseline and/or full-pipeline evaluation on a dataset:

1. Backend and worker must be running (locally or in Docker).
2. From the **backend** directory (with `PYTHONPATH` set so that `app` is importable):

```bash
cd backend
set PYTHONPATH=%CD%           # Windows
# export PYTHONPATH=$(pwd)    # Linux/macOS
python scripts/run_evaluation.py --dataset data/eval_questions.json --mode both --name "My run"
```

Options:

- `--dataset` – Path to a JSON file: array of `{"query": "..."}` (optional `expected_label`).
- `--mode` – `baseline` | `full_pipeline` | `both`.
- `--name` – Optional run name.
- `--base-url` – Backend URL (default `http://localhost:8000`).
- `--timeout` – Per-question timeout in seconds for the full pipeline (default 300).

Results are stored in the database. View them in the frontend under the **Evaluation** tab.

---

## 7. Quick reference – run order

| Step | Command / action |
|------|-------------------|
| 1 | Copy `.env.example` → `.env` and set `DATABASE_URL`, `REDIS_URL`, and one LLM key |
| 2 | `pip install -r requirements.txt` |
| 3 | From `backend/`: set `PYTHONPATH`, run `alembic upgrade head` |
| 4 | Start API: from `backend/`, `uvicorn app.main:app --reload --port 8000` |
| 5 | Start worker: from `backend/`, `python worker.py` |
| 6 | Frontend: from `frontend/`, `npm install` then `npm run dev` |
| 7 | Open http://localhost:5173 |

---

## 8. Troubleshooting

| Issue | What to check |
|-------|----------------|
| **“No LLM provider configured”** | Set either `OPENAI_API_KEY` or `GEMINI_API_KEY` in `.env`. |
| **DB connection errors** | Verify PostgreSQL is running and `DATABASE_URL` (user, password, host, port, db name) is correct. |
| **Redis connection errors** | Verify Redis is running and `REDIS_URL` is correct. |
| **Workflow stays CREATED / never progresses** | The RQ worker must be running; check the terminal where you started `python worker.py`. |
| **CORS errors in browser** | Set `FRONTEND_ORIGIN` to the exact origin of the frontend (e.g. `http://localhost:5173`). |
| **Migrations fail (ModuleNotFoundError: app)** | Run Alembic from the `backend/` directory with `PYTHONPATH` set to `backend/`. |
| **Docker: frontend can’t reach API** | Build frontend with `VITE_API_BASE_URL=http://localhost:8000` so the browser (on the host) calls the host’s port 8000. |

---

## 9. Architecture and methodology (mapping to design)

- **Pipeline**: User → Planner → Generator → Claim Extractor → Retriever → Verifier → Critic → Refiner → final answer (with evidence and confidence). See `docs/roadmap.md` and the project PDF.
- **Claim extraction**: Generator output → LLM-based extraction of atomic claims → stored in `claims`; see `backend/app/agents/claim_extractor.py` and `backend/app/llm.py` (`extract_claims_from_text`).
- **Verification**: Per claim, evidence is retrieved (currently placeholder in `backend/app/retrieval.py`); LLM NLI-style verification in `backend/app/llm.py` (`verify_claim_with_evidence`); results in `verification` table.
- **Evaluation**: Script runs baseline (single LLM) and/or full pipeline on a question set; metrics (claim verification accuracy, precision/recall/F1, success rates) in `backend/app/evaluation_metrics.py`; runs stored in `evaluation_runs` and `evaluation_samples`; see Phase 8 in `docs/roadmap.md`.

For a phased breakdown of what is implemented, see `docs/roadmap.md` and the main `README.md`.

---

## 10. Summary – commands to get running

**Option A – Local (no Docker)**

```text
# 1. Env
cp .env.example .env
# Edit .env: DATABASE_URL, REDIS_URL, OPENAI_API_KEY or GEMINI_API_KEY

# 2. Backend
pip install -r requirements.txt
cd backend
# Windows: set PYTHONPATH=%CD%
# Linux/macOS: export PYTHONPATH=$(pwd)
alembic upgrade head
uvicorn app.main:app --reload --port 8000
# Leave running; in a new terminal:
python worker.py

# 3. Frontend (new terminal)
cd frontend
npm install
npm run dev
# Open http://localhost:5173
```

**Option B – Docker**

```text
cp .env.example .env
# Edit .env: set OPENAI_API_KEY or GEMINI_API_KEY
docker compose up --build
# Open http://localhost:5173 and http://localhost:8000/docs
```
