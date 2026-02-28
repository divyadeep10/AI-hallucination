# Docker

Phase 9 adds Docker support at the **project root**:

- **docker-compose.yml** (in repo root) – runs Postgres, Redis, backend API, RQ worker, and frontend.
- **backend/Dockerfile** – API and worker image (entrypoint runs migrations then starts the process).
- **frontend/Dockerfile** – Multi-stage build and nginx serve.

From the project root:

```bash
cp .env.example .env
# Edit .env: set OPENAI_API_KEY or GEMINI_API_KEY (and optionally POSTGRES_*)
docker compose up --build
```

Then open http://localhost:5173 (frontend) and http://localhost:8000/docs (API).

Full details: **[docs/SETUP_AND_RUN.md](../docs/SETUP_AND_RUN.md)** (§5).
