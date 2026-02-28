# Self-Correcting Multi-Agent AI System — Project Guide

This document is both a **non-technical overview** and a **technical reference** for the project. It describes what the product does, how it works, how it was built in line with the design document (`docs/Self-Correcting Multi-Agent AI System.pdf`), and where everything lives in the codebase.

---

## Part 1: Non-technical overview

### What is this product?

The **Self-Correcting Multi-Agent AI System** is an AI application that:

1. **Answers your questions** using a large language model (e.g. OpenAI or Google Gemini).
2. **Checks its own answer** by breaking it into small factual “claims” and verifying each one against evidence.
3. **Improves the answer** using a “critic” that spots weak or wrong parts and a “refiner” that rewrites the answer to be more accurate and grounded.

So instead of a single black-box reply, you get a **final answer that has been verified and refined**, plus a **transparent view** of how each step worked (claims, evidence, verification status).

### Who is it for?

- **End users**: Ask a question and get a verified, refined answer; optionally explore how the system reached it.
- **Developers / evaluators**: Run evaluations (baseline vs full pipeline), inspect workflows, claims, evidence, and metrics.
- **Researchers / students**: Use the design document (PDF) and this codebase to see a concrete implementation of a multi-agent, self-correcting pipeline.

### How do I use it?

- **Web UI**: Open the dashboard, type a question, and either get a quick “baseline” answer or run the “full pipeline” (plan → generate → extract claims → retrieve evidence → verify → critique → refine). Then use the **Query** tab to see the answer and the **Evaluation** tab to compare runs.
- **Setup**: Copy `.env.example` to `.env`, set your database, Redis, and at least one LLM API key. Run the backend, the background worker, and the frontend (or use Docker). Full steps are in **docs/SETUP_AND_RUN.md**.

---

## Part 2: Workflows and how the product works

### High-level pipeline (aligned with the design PDF)

The design document describes a pipeline that goes from the user’s question to a final, evidence-aware answer. This project implements that flow as follows:

```
User question
    → Planner (prepares workflow)
    → Generator (draft answer)
    → Claim Extractor (atomic factual claims)
    → Retriever (evidence per claim)
    → Verifier (support / contradict / uncertain per claim)
    → Critic (feedback on draft using verification)
    → Refiner (final answer using draft + critique + verified claims)
    → Final answer (+ evidence and confidence)
```

- **Baseline path**: One LLM call returns an answer immediately (no verification). Used for comparison and quick replies.
- **Full pipeline**: All steps above run asynchronously via a job queue; the UI polls until the workflow reaches “Refined” and then shows the refined answer and transparency data (claims, evidence, verification).

### Workflow states (in code and DB)

A **workflow** is one run for one user question. Its status moves through:

`CREATED` → `PLANNED` → `GENERATED` → `CLAIMS_EXTRACTED` → `EVIDENCE_RETRIEVED` → `VERIFIED` → `CRITIC_REVIEWED` → `REFINED` (and optionally `COMPLETED` or `FAILED`).

Each agent advances the workflow to the next state when it finishes. The frontend **timeline** shows these stages and, where available, timestamps (from stored responses).

### Data flow (simplified)

1. **Question** is stored on the `Workflow` row.
2. **Draft answer** from the Generator is stored in `Response` (agent_type = GENERATOR).
3. **Claims** extracted from that draft are stored in `Claim` (with entities and extraction_confidence).
4. **Evidence** for each claim is stored in `Evidence` (snippet, source_url, retrieval_score).
5. **Verification** per claim is stored in `Verification` (status: SUPPORTED / CONTRADICTED / UNCERTAIN / NO_EVIDENCE, confidence_score).
6. **Critique** and **refined answer** are stored as further `Response` rows (CRITIC, REFINER).

The UI can show: draft, claims (with coloured verification status), evidence per claim, critique, and final refined answer.

---

## Part 3: Tech stack and project structure

### Tech stack

| Layer        | Technology |
|-------------|------------|
| Backend API | FastAPI, Python 3.10+ |
| Database    | PostgreSQL, SQLAlchemy ORM, Alembic migrations |
| Queue       | Redis, RQ (background jobs for agents) |
| LLM         | OpenAI-compatible API and/or Google Gemini (env-configured) |
| Frontend    | React 18, TypeScript, Vite |
| Deployment  | Docker Compose (Postgres, Redis, backend, worker, frontend) |

### Project structure (where to find what)

```
major_project/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, CORS, routers
│   │   ├── config.py            # Central env-based config (Phase 9)
│   │   ├── db.py                # SQLAlchemy engine, session, get_db
│   │   ├── llm.py               # LLM: generate_answer, extract_claims_from_text, verify_claim_with_evidence
│   │   ├── retrieval.py         # Evidence retrieval API (placeholder; plug BM25/embeddings here)
│   │   ├── evaluation_metrics.py # Claim-level and run-level metrics (Phase 8)
│   │   ├── models/              # ORM: Workflow, Response, Claim, Evidence, Verification, EvaluationRun, EvaluationSample
│   │   ├── schemas.py           # Pydantic request/response models
│   │   ├── routes/
│   │   │   ├── query.py         # /api/query, /api/workflows, /api/workflows/{id}, .../responses, .../claims, .../debug
│   │   │   └── evaluations.py  # /api/evaluations/runs, .../runs/{id}
│   │   └── agents/              # Planner, Generator, ClaimExtractor, Retriever, Verification, Critic, Refiner
│   ├── alembic/                 # Migrations (workflows → responses → claims → evidence → verification → evaluation_*)
│   ├── scripts/
│   │   └── run_evaluation.py    # CLI: run baseline and/or full pipeline on a JSON dataset (Phase 8)
│   ├── data/
│   │   └── eval_questions.json  # Example evaluation dataset
│   ├── worker.py                # RQ worker entry (processes agent jobs)
│   ├── Dockerfile               # Backend + worker image; entrypoint runs migrations then CMD
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # Tabs: Query (form, answer, workflow, timeline, claims, debug), Evaluation (runs, metrics, samples)
│   │   ├── api.ts               # API client (query, workflows, responses, claims, evidence, debug, evaluations)
│   │   └── styles.css           # Layout, cards, timeline, claim status colours, evaluation UI
│   ├── Dockerfile               # Multi-stage: build (Vite), serve (nginx)
│   └── package.json
├── docs/
│   ├── roadmap.md               # Phased plan (0–9) and what each phase implements
│   ├── SETUP_AND_RUN.md         # Install, env, run locally/Docker, evaluation script, troubleshooting
│   └── Self-Correcting Multi-Agent AI System.pdf  # Design document (reference)
├── docker-compose.yml           # Postgres, Redis, backend, worker, frontend
├── .env.example                 # Env vars (DB, Redis, LLM, CORS, optional Docker)
├── README.md                    # Status, phase list, quick run, link to SETUP_AND_RUN
└── PROJECT_README.md            # This file: product overview + technical guide
```

---

## Part 4: Mapping the code to the design document (PDF)

The design document describes a self-correcting pipeline with planning, generation, claim extraction, retrieval, verification, critique, and refinement. Below is how each part of that design is implemented in this repo.

### Planning and orchestration (PDF: pipeline overview)

- **Planner**: `backend/app/agents/planner.py` — moves workflow from CREATED to PLANNED. Designed so it can later be extended to decompose the query into subtasks.
- **Orchestration**: `backend/app/routes/query.py` — `POST /api/workflows` creates a workflow and enqueues planner → generator → claim_extractor → retriever → verification → critic → refiner on the RQ queue. Worker runs these in order via `backend/worker.py`.

### Generation (PDF: draft answer)

- **Generator**: `backend/app/agents/generator.py` — runs when status is PLANNED; calls `app/llm.generate_answer(user_query)` and saves the result in `Response` with agent_type GENERATOR; sets status to GENERATED.
- **LLM**: `backend/app/llm.py` — `generate_answer` uses OpenAI-compatible or Gemini (env: OPENAI_API_KEY / GEMINI_API_KEY). Single place for model and prompt for the draft.

### Claim extraction (PDF §20)

- **Claim Extractor**: `backend/app/agents/claim_extractor.py` — runs when status is GENERATED; loads the latest GENERATOR response; calls `app/llm.extract_claims_from_text(text)`; deduplicates by normalized claim text; writes rows to `Claim` (claim_text, entities, extraction_confidence); sets status to CLAIMS_EXTRACTED.
- **LLM**: `app/llm.py` — `extract_claims_from_text` prompts the LLM for a JSON array of claims; `_parse_claims_json` normalizes and validates; empty or parse errors return [].

### Retrieval (PDF §21)

- **Retriever**: `backend/app/agents/retriever.py` — runs when status is CLAIMS_EXTRACTED; for each claim of the workflow, calls `app/retrieval.retrieve_evidence_for_claim(claim_text)`; stores results in `Evidence` (snippet, source_url, retrieval_score); sets status to EVIDENCE_RETRIEVED.
- **Retrieval API**: `backend/app/retrieval.py` — `retrieve_evidence_for_claim` is the single entry point. Current implementation is a placeholder (returns the claim text as one snippet). The design allows plugging in hybrid retrieval (e.g. BM25 + embeddings) here without changing callers.

### Verification (PDF §22)

- **Verifier**: `backend/app/agents/verification.py` — runs when status is EVIDENCE_RETRIEVED; for each claim, takes the top evidence (by retrieval_score); calls `app/llm.verify_claim_with_evidence(claim_text, evidence.snippet)`; writes `Verification` (status: SUPPORTED / CONTRADICTED / UNCERTAIN / NO_EVIDENCE, confidence_score); sets workflow to VERIFIED. Handles missing evidence (NO_EVIDENCE) and LLM errors (UNCERTAIN).
- **LLM**: `app/llm.py` — `verify_claim_with_evidence` uses an NLI-style prompt and parses JSON (status, confidence). Returns status as given by the LLM (SUPPORTED, etc.) so the UI and evaluation metrics can show green/red/amber consistently.

### Critic and refinement (PDF §23)

- **Critic**: `backend/app/agents/critic.py` — runs when status is VERIFIED; loads the draft (GENERATOR or BASELINE) and **only verifications and claims for this workflow**; builds a prompt with draft + per-claim verification status; calls `generate_answer`; stores result in `Response` (CRITIC); sets status to CRITIC_REVIEWED.
- **Refiner**: `backend/app/agents/refiner.py` — runs when status is CRITIC_REVIEWED; loads draft, CRITIC response, and **only verifications/claims/evidence for this workflow**; prompts to use only SUPPORTED claims as factual and to downplay or correct others; calls `generate_answer`; stores result in `Response` (REFINER); sets status to REFINED.

(Scoping critic and refiner to the current workflow avoids mixing data from other runs.)

### Transparency and evaluation (PDF: evidence, confidence, evaluation)

- **API**: `GET /api/workflows/{id}/responses`, `.../claims`, `.../debug`, `GET /api/claims/{id}/evidence` expose all stored data for a run. Claims include verification_status and verification_confidence.
- **Frontend**: Query tab shows timeline, stored responses, claims with coloured verification status (SUPPORTED=green, CONTRADICTED=red, UNCERTAIN/NO_EVIDENCE=amber), expandable evidence and scores, and developer raw-JSON views.
- **Evaluation**: `backend/scripts/run_evaluation.py` runs baseline and/or full pipeline on a JSON dataset; `app/evaluation_metrics.py` computes claim-level and run-level metrics (e.g. claim_verification_accuracy, precision/recall/F1); results stored in `evaluation_runs` and `evaluation_samples`; frontend Evaluation tab lists runs and shows summary metrics and samples.

---

## Part 5: Configuration and deployment

- **Configuration**: All env-based settings are centralized in `backend/app/config.py` (database, Redis, CORS, LLM keys and endpoints). `.env.example` lists every variable and how to switch providers (OpenAI vs Gemini).
- **Secrets**: Never commit `.env`. Use it for DATABASE_URL, REDIS_URL, OPENAI_API_KEY or GEMINI_API_KEY, and optional overrides.
- **Docker**: Root `docker-compose.yml` runs Postgres, Redis, backend (with migration entrypoint), worker, and frontend. See **docs/SETUP_AND_RUN.md** for build/run and **docker/README.md** for a short pointer.

---

## Part 6: Summary

| Topic | Where to look |
|-------|----------------|
| What the product does (plain language) | Part 1 above |
| Pipeline and workflow states | Part 2 |
| Tech stack and folder layout | Part 3 |
| How the PDF design is implemented in code | Part 4 |
| Env vars and Docker | Part 5, .env.example, docs/SETUP_AND_RUN.md |
| Run instructions and troubleshooting | docs/SETUP_AND_RUN.md |
| Phase-by-phase implementation list | docs/roadmap.md |
| Quick start and phase summary | README.md |

The codebase is structured so that each stage of the design document (planning, generation, claim extraction, retrieval, verification, critique, refinement, transparency, evaluation) has a clear place in the backend and frontend, with edge cases (empty query, missing evidence, LLM failures, workflow scoping) handled in the agents and API.
