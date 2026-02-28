Self-Correcting Multi-Agent AI System
=====================================

This repository contains a multi-agent, self-correcting AI system that generates
responses, extracts factual claims, verifies them against external evidence,
and iteratively refines answers before returning them to the user.

The design and roadmap are based on the project document
`docs/Self-Correcting Multi-Agent AI System.pdf`. For a full **technical and non-technical** guide (workflows, tech stack, project structure, and how the code maps to the design PDF), see **[PROJECT_README.md](PROJECT_README.md)**.

Current Status (Through Phase 9 – Product ready)
-----------------------------------------------

- **Phases 0–9** implemented. The system is runnable locally or via Docker.
- **Backend** (`backend/`): FastAPI, PostgreSQL (Alembic), Redis/RQ, LLM (OpenAI or Gemini), agents (Planner → Generator → Claim Extractor → Retriever → Verifier → Critic → Refiner), evaluation API and metrics.
- **Frontend** (`frontend/`): React + Vite dashboard (Query, workflow timeline, claims/evidence, developer debug, Evaluation tab).
- **Config**: Centralized in `backend/app/config.py`; copy `.env.example` to `.env` and set `DATABASE_URL`, `REDIS_URL`, and at least one LLM key.
- **Docker**: `docker-compose.yml` plus Dockerfiles for backend, worker, and frontend (see [Setup and run](#setup-and-run)).

**Full setup, install commands, and troubleshooting:** see **[docs/SETUP_AND_RUN.md](docs/SETUP_AND_RUN.md)**.

Phase 1 – Baseline LLM API and UI
---------------------------------

Phase 1 adds a thin vertical slice for a single-pass LLM response with a simple
web UI:

- Backend endpoints:
  - `POST /api/query`
    - Request body: `{"query": "<user question>"}`.
    - Behaviour:
      - Creates a new workflow row in the database with status `CREATED`.
      - Calls the configured LLM provider (OpenAI-compatible if `OPENAI_API_KEY`
        is set, otherwise Gemini if `GEMINI_API_KEY` is set).
      - Updates workflow status to `COMPLETED` and sets `completed_at`.
      - Returns the generated `answer` and `workflow_id`.
    - Response body (simplified):
      - `{"workflow_id": 1, "answer": "...", "status": "COMPLETED"}`

  - `GET /api/workflows/{workflow_id}`
    - Returns basic status for a workflow:
      - `workflow_id`, `status`, `created_at`, `completed_at`.

- Frontend (Vite + React in `frontend/`):
  - A single-page UI with:
    - Text area to enter a question.
    - Submit button to call `POST /api/query`.
    - Answer panel showing the returned text from the LLM.
    - Workflow status panel showing the workflow ID and status, with a button
      that calls `GET /api/workflows/{id}` to refresh status.
  - The frontend reads `VITE_API_BASE_URL` to locate the backend API and
    defaults to `http://localhost:8000` for local development.

Phase 2 – Orchestration & Async Workflow Engine
-----------------------------------------------

Phase 2 introduces the asynchronous orchestration layer using Redis + RQ:

- Workflow states are formalised in code (`WorkflowStatus`): `CREATED`, `PLANNED`,
  `GENERATED`, `CLAIMS_EXTRACTED`, `EVIDENCE_RETRIEVED`, `VERIFIED`,
  `CRITIC_REVIEWED`, `REFINED`, `COMPLETED`, `FAILED`.
- A Redis-backed RQ queue (name configurable via `WORKFLOW_QUEUE_NAME`) is used
  to run background agents.
- A generic `Agent` base class is defined, and the first concrete agent,
  `PlannerAgent`, is implemented.
  - In this phase, `PlannerAgent` performs a minimal transition from
    `CREATED` to `PLANNED` for a workflow.
- New API endpoint for asynchronous orchestration:
  - `POST /api/workflows`
    - Creates a new workflow with status `CREATED` and enqueues planner →
      generator → claim extractor jobs on the RQ queue (see Phase 3 and 4).
    - Returns the initial workflow status (typically `CREATED`).

Phase 3 – Generator Agent & Draft Responses
-------------------------------------------

Phase 3 adds persistent response storage and a generator agent:

- Database:
  - A `responses` table stores generated outputs from agents with fields:
    - `id`, `workflow_id`, `agent_type`, `response_text`, `model_used`, `timestamp`.
- Agents:
  - `GeneratorAgent` is introduced to run as a background job:
    - Operates on workflows in the `PLANNED` state.
    - Uses the shared LLM generation function to produce a draft answer.
    - Persists the answer in `responses` with `agent_type="GENERATOR"` and
      moves the workflow status to `GENERATED`.
- API:
  - `POST /api/workflows` enqueues planner and generator agents in sequence;
    Phase 4 adds the claim extractor to this chain.
  - `GET /api/workflows/{workflow_id}/responses` returns all stored responses
    (baseline and generator outputs) for a workflow.
  - `POST /api/query` also persists its synchronous baseline answer to the
    `responses` table with `agent_type="BASELINE"`, enabling later comparison.

The frontend exposes a “Stored Responses” view that fetches and displays
responses for the current workflow, allowing you to inspect baseline and (later)
agent-generated drafts separately from the final verified answer.

Phase 4 – Claim Extraction Pipeline
-----------------------------------

Phase 4 adds claim-level extraction from the generator draft (PDF §20):

- Database: A `claims` table with `id`, `response_id`, `claim_text`, `entities` (JSON), `extraction_confidence`.
- LLM: `extract_claims_from_text(text)` in `app.llm` returns a list of claim dicts; handles empty input and parse errors.
- Agent: `ClaimExtractionAgent` runs after generator, extracts claims from the latest GENERATOR response, normalizes and deduplicates, then sets workflow to `CLAIMS_EXTRACTED`.
- API: `POST /api/workflows` enqueues planner → generator → claim extractor. `GET /api/workflows/{workflow_id}/claims` returns extracted claims.
- Frontend: "Load Claims" button and list showing claim text, entities, and confidence.

Phase 5 – Retrieval Layer (Hybrid-ready)
----------------------------------------

Phase 5 introduces the evidence retrieval layer (PDF §21):

- Database: An `evidence` table with `id`, `claim_id`, `source_url`, `snippet`, `retrieval_score`.
- Retrieval module: `retrieve_evidence_for_claim` in `app.retrieval` defines the hybrid
  retrieval API. The current implementation returns a safe placeholder snippet based
  on the claim text and is structured so it can be replaced with a real BM25 +
  embeddings retriever later.
- Agent: `RetrieverAgent` runs after claim extraction, iterates over all claims for a
  workflow, calls the retrieval module, stores `Evidence` rows, and moves the workflow
  to `EVIDENCE_RETRIEVED`.
- API: `POST /api/workflows` enqueues planner → generator → claim extractor → retriever.
  `GET /api/claims/{claim_id}/evidence` returns evidence items for a claim.
- Frontend: Each claim in the "Extracted Claims" list has a "Load Evidence" button that
  fetches and displays snippets, source URLs (when present), and retrieval scores.

Phase 6 – Verification, Critic, and Refinement
----------------------------------------------

Phase 6 adds claim-level verification and refinement (PDF §22–23):

- Database: A `verification` table with `id`, `claim_id`, `status`, `confidence_score`,
  `evidence_id`.
- Verification: `verify_claim_with_evidence` in `app.llm` uses the configured LLM as an
  NLI-style verifier, returning structured JSON (status and confidence) per claim+evidence.
- Agents:
  - `VerificationAgent` runs after retrieval and writes one verification row per claim,
    handling missing evidence and failures (NO_EVIDENCE / UNCERTAIN) and moving the workflow
    to `VERIFIED`.
  - `CriticAgent` consumes the draft answer and verification results to produce a critique
    stored as a CRITIC response, moving the workflow to `CRITIC_REVIEWED`.
  - `RefinementAgent` uses the draft answer, critic feedback, verified claims, and evidence
    to generate a refined answer stored as a REFINER response, moving the workflow to `REFINED`.
- API / Frontend:
  - `GET /api/workflows/{workflow_id}/claims` now includes optional verification_status and
    verification_confidence per claim, so the UI can surface which claims are verified,
    uncertain, or contradicted.

Phase 7 – Frontend: Full Transparency Dashboard
------------------------------------------------

Phase 7 adds a transparency-focused UI (roadmap §7.1–7.3):

- **Workflow timeline**: Pipeline stages (Planner → Generator → Claim extraction → Retrieval →
  Verification → Critic → Refiner) are shown with completed/pending state and timestamps
  (from stored responses where available). Current workflow status is displayed as a badge.
- **Claim-level explanation**: Each claim is shown with a colored status (SUPPORTED=green,
  CONTRADICTED=red, UNCERTAIN/NO_EVIDENCE=amber). Clicking a claim expands evidence snippets
  and verification score.
- **Developer mode**: A toggle plus “Load raw JSON” fetches the full debug payload. Tabs show
  raw JSON for workflow, responses, claims, and verifications (from `GET /api/workflows/{id}/debug`).
- **Async pipeline from UI**: “Run full pipeline (async)” button starts a workflow via
  `POST /api/workflows` so users can run the full multi-agent pipeline and then refresh status,
  load responses/claims, and use the timeline and developer views.

Phase 8 – Evaluation & Metrics Tools
-----------------------------------

Phase 8 adds evaluation runs and a result summary UI:

- **Database**: `evaluation_runs` and `evaluation_samples` tables (migration `0006_create_evaluation_tables`) store run metadata, per-question workflow ids, answers, statuses, and metrics.
- **Metrics**: Claim verification accuracy, supported/contradicted rate, precision/recall/F1; baseline vs system success counts. Logic in `app.evaluation_metrics`.
- **Script**: `backend/scripts/run_evaluation.py` runs baseline and/or full pipeline on a JSON dataset, polls until workflows complete, and persists results. Example: `python scripts/run_evaluation.py --dataset data/eval_questions.json --mode both`.
- **API**: `GET /api/evaluations/runs` and `GET /api/evaluations/runs/{id}` for listing and run detail.
- **Frontend**: "Evaluation" tab lists runs; selecting a run shows summary metrics (cards and bar charts) and a samples table.

Phase 9 – Packaging, Deployment, and Polish
-------------------------------------------

- **Dockerization**: `backend/Dockerfile` (API + worker image; entrypoint runs migrations then CMD), `frontend/Dockerfile` (multi-stage build + nginx). Root `docker-compose.yml` runs Postgres, Redis, backend, worker, frontend.
- **Configuration**: `backend/app/config.py` centralizes env-based settings; `.env.example` documents all variables. Switching LLM: set `OPENAI_API_KEY` or `GEMINI_API_KEY` (and optional base/model); see docs/SETUP_AND_RUN.md.
- **Documentation**: Architecture and methodology mapped in docs/SETUP_AND_RUN.md (§9); claim extraction, verification, retrieval, and evaluation steps align with the design PDF and roadmap.

Architecture and methodology (mapping to design)
-----------------------------------------------

- **Pipeline** (see design PDF): User → Planner → Generator → Claim Extractor → Retriever → Verifier → Critic → Refiner → final answer (with evidence and confidence). Implemented in `backend/app/agents/` and `backend/app/routes/query.py`.
- **Claim extraction**: Generator output → LLM-based extraction (`app/llm.extract_claims_from_text`) → stored in `claims`; agent in `agents/claim_extractor.py`.
- **Verification**: Evidence per claim (placeholder in `app/retrieval`; pluggable); NLI-style verification in `app/llm.verify_claim_with_evidence`; results in `verification` table; agent in `agents/verification.py`.
- **Evaluation**: Script `backend/scripts/run_evaluation.py` runs baseline and/or full pipeline; metrics in `app/evaluation_metrics.py`; runs in `evaluation_runs` / `evaluation_samples`; frontend Evaluation tab.

Setup and run
-------------

**Quick (local):** Copy `.env.example` to `.env`, set `DATABASE_URL`, `REDIS_URL`, and one LLM key. Install backend deps, run migrations, start API and worker, then run frontend. See **[docs/SETUP_AND_RUN.md](docs/SETUP_AND_RUN.md)** for exact commands (Windows and Unix), Docker Compose, evaluation script, and troubleshooting.

**Docker:** From project root, `docker compose up --build`. Open http://localhost:5173 (frontend) and http://localhost:8000/docs (API).

Running the Backend (development)
---------------------------------

1. Create `.env` from `.env.example`; set `DATABASE_URL`, `REDIS_URL`, and one of `OPENAI_API_KEY` / `GEMINI_API_KEY`.
2. `pip install -r requirements.txt`
3. From `backend/` with `PYTHONPATH` set to `backend`: `alembic upgrade head`
4. Start Redis (e.g. local or Docker).
5. From `backend/`: `uvicorn app.main:app --reload --port 8000`
6. In a second terminal, from `backend/`: `python worker.py`

Running the Frontend (development)
----------------------------------

From `frontend/`: `npm install` then `npm run dev`. Open http://localhost:5173. Set `FRONTEND_ORIGIN` in `.env` if you use a different origin.

Refer to **[docs/SETUP_AND_RUN.md](docs/SETUP_AND_RUN.md)** for full step-by-step instructions, Docker, evaluation script, and troubleshooting, and to **docs/roadmap.md** for the phased implementation plan.

