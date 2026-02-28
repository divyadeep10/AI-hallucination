High-Level Idea
You’re building a multi-agent, self-correcting AI pipeline that goes:
User → Planner → Generator → Claim Extractor → Retriever → Verifier → Critic → Refiner → Final Answer (+ evidence, confidence), with a web dashboard and async backend.
Below is a phased roadmap, broken into small, code-friendly iterations so we can implement each step in short sessions without heavy load.
Phase 0 – Project Foundations (Very Small Steps) [IMPLEMENTED]
0.1 – Tech & Repo Skeleton
- Stack decided: FastAPI backend, PostgreSQL, Redis/RQ (later phase), FAISS/Chroma (later phase), React frontend.
- Repo structure created: backend/, frontend/, docker/, docs/.
0.2 – Environment & Config
- Added requirements.txt, frontend/package.json, basic .env.example.
- Root README documents how to run the backend (planned) and references the roadmap and PDF design document.
0.3 – Database Bootstrap
- Minimal DB schema implemented: workflows table with id, user_query, status, created_at, completed_at.
- Alembic configured under backend/alembic with an initial migration that creates the workflows table.
Phase 1 – Thin Vertical Slice (Baseline LLM System) [IMPLEMENTED]
1.1 – Minimal API Endpoint
- Implemented as `POST /api/query` that creates a workflow row and, for now, calls a single LLM
  (OpenAI-compatible or Gemini, chosen based on available API keys) to return an answer directly.
1.2 – Simple Frontend Screen
- Implemented as a Vite + React single-page UI (in `frontend/`) with an input box, submit button,
  answer display, and workflow status panel that can refresh status via the backend.
1.3 – Logging & Basic Status
- Workflows table tracks status (`CREATED`, `COMPLETED`) and timestamps.
- Implemented as `GET /api/workflows/{id}` for status polling.
(After Phase 1, you have a working “single-LLM baseline” for later comparison.)
Phase 2 – Orchestration & Async Workflow Engine [IMPLEMENTED]
2.1 – Workflow States & ORM Models
- Workflow status transitions are represented as a `WorkflowStatus` enum in code, covering:
  CREATED → PLANNED → GENERATED → CLAIMS_EXTRACTED → EVIDENCE_RETRIEVED → VERIFIED →
  CRITIC_REVIEWED → REFINED → COMPLETED, plus FAILED.
2.2 – Async Queue Integration
- Redis + RQ queue integrated via `REDIS_URL` and `WORKFLOW_QUEUE_NAME`.
- A dedicated worker (`backend/worker.py`) processes queued jobs.
- A new `POST /api/workflows` endpoint creates a workflow and enqueues a planner job instead
  of doing everything inline.
2.3 – Agent Abstraction Layer
- A generic `Agent` base class defines the interface for all agents.
- A concrete `PlannerAgent` is implemented that moves workflows from CREATED to PLANNED
  when executed by the worker.
Phase 3 – Generator Agent & Draft Responses [IMPLEMENTED]
3.1 – Response/Task Models
- A `responses` table has been added with fields analogous to the design document:
  - `id` (response_id), `workflow_id`, `agent_type`, `response_text`, `model_used`, `timestamp`.
- A separate tasks model is deferred until planning becomes more complex.
3.2 – Generator Agent Worker
- A `GeneratorAgent` has been implemented that:
  - Operates on workflows in the `PLANNED` state.
  - Calls the shared LLM to produce a draft answer.
  - Saves the draft to the `responses` table.
  - Moves the workflow status to `GENERATED`.
- The asynchronous endpoint `POST /api/workflows` now enqueues both the planner and
  generator agents in sequence, mirroring the Planner → Generator stages in the PDF.
3.3 – Frontend Draft View
- The frontend includes a "Stored Responses" view that:
  - Calls `GET /api/workflows/{id}/responses` to list all responses (baseline and generator).
  - Displays agent type, timestamp, model_used, and the raw response text separately from
    the main answer panel.
Phase 4 – Claim Extraction Pipeline [IMPLEMENTED]
4.1 – Claims Table & Schema
- claims table: id, response_id, claim_text, entities (JSON), extraction_confidence. Migration 0003.
4.2 – Claim Extraction Agent
- ClaimExtractionAgent: runs when GENERATED; loads latest GENERATOR response; extract_claims_from_text(); normalize and dedupe; persist claims; set CLAIMS_EXTRACTED.
4.3 – Basic Claims UI
- "Load Claims" button and list (claim text, entities, confidence). GET /api/workflows/{id}/claims.
Phase 5 – Retrieval Layer (Hybrid: Embeddings + BM25) [IMPLEMENTED - STRUCTURE]
5.1 – Knowledge Base Setup
- Retrieval module and data model prepared for hybrid retrieval. Actual corpus and
  FAISS/BM25 integration can be plugged into `app.retrieval.retrieve_evidence_for_claim`.
5.2 – Evidence Table & Models
- `evidence` table added with fields: id (evidence_id), claim_id, source_url, snippet,
  retrieval_score. See migration 0004_create_evidence_table and `Evidence` model.
5.3 – Retrieval Agent
- `RetrieverAgent` implemented. For each claim belonging to a workflow, calls the
  retrieval module, stores evidence rows, and transitions workflow to
  EVIDENCE_RETRIEVED. Current placeholder retriever echoes the claim text as a snippet.
5.4 – Evidence Visualization
- Frontend adds \"Load Evidence\" controls on each claim, calling
  `GET /api/claims/{claim_id}/evidence` and displaying snippets, source URLs, and scores.
Phase 6 – Verification, Critic, and Refinement [IMPLEMENTED]
6.1 – Verification Table & NLI Integration
- `verification` table added with id (verification_id), claim_id, status, confidence_score, evidence_id.
- NLI-style verification implemented via the existing LLM using a structured JSON protocol
  (`verify_claim_with_evidence` in `app.llm`).
6.2 – Verification Agent
- `VerificationAgent` runs after evidence retrieval. For each claim + top evidence, computes
  verification status and confidence, writes a row in `verification`, and moves the workflow
  to VERIFIED. Handles missing evidence and LLM failures gracefully (NO_EVIDENCE / UNCERTAIN).
6.3 – Critic Agent
- `CriticAgent` reads the draft answer and verification results and produces structured feedback,
  stored as a CRITIC response. Workflow moves to CRITIC_REVIEWED.
6.4 – Refinement Agent
- `RefinementAgent` uses the draft answer, critic feedback, verified claims, and evidence to
  generate a refined answer stored as a REFINER response and moves the workflow to REFINED.
Phase 7 – Frontend: Full Transparency Dashboard [IMPLEMENTED]
7.1 – Workflow Timeline View
- Pipeline timeline shows each stage (Planner, Generator, Claim extraction, Retrieval, Verification, Critic, Refiner) with completed/pending state and timestamps where available (from stored responses and workflow created_at).
7.2 – Claim-Level Explanation UI
- Claims list shows each claim with colored left border and badge by verification status (SUPPORTED=green, CONTRADICTED=red, UNCERTAIN/NO_EVIDENCE=amber). Click to expand evidence snippets and verification score.
7.3 – Developer/Debug Views
- Developer mode toggle and “developer mode” button; tabs for Workflow, Responses, Claims, Verifications showing raw JSON via GET /api/workflows/{id}/debug.
Phase 8 – Evaluation & Metrics Tools [IMPLEMENTED]
8.1 – Baseline vs System Evaluation Script
- Script `backend/scripts/run_evaluation.py`: runs baseline (POST /api/query) and/or full pipeline (POST /api/workflows + poll) on a JSON dataset; supports --mode baseline | full_pipeline | both, --dataset path, --name, --timeout.
8.2 – Metrics Computation
- Per-sample: num_claims, num_supported/contradicted/uncertain, claim_verification_accuracy, precision/recall/F1. Run-level aggregation in `app.evaluation_metrics`. Results stored in evaluation_runs and evaluation_samples tables.
8.3 – Result Summary Page
- Frontend "Evaluation" tab: list runs (GET /api/evaluations/runs), run detail with metric cards, bar charts (baseline vs system success rate, claim verification accuracy), and samples table.
Phase 9 – Packaging, Deployment, and Polish [IMPLEMENTED]
9.1 – Dockerization
- Backend Dockerfile (API + worker image; entrypoint runs migrations then CMD). Frontend Dockerfile (multi-stage build, nginx serve). Root docker-compose.yml: Postgres, Redis, backend, worker, frontend; healthchecks and env from .env.
9.2 – Configuration & Secrets
- Central config in backend/app/config.py; db and queue use config; .env.example documents all vars and how to switch OpenAI vs Gemini.
9.3 – Documentation & Final Report Hooks
- docs/SETUP_AND_RUN.md: full setup, install commands, run locally/Docker, evaluation script, troubleshooting; README: architecture/methodology mapping (pipeline, claim extraction, verification, evaluation); link to setup guide.