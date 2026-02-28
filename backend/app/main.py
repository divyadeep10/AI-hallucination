from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import FRONTEND_ORIGIN
from app.routes import query_router, evaluations_router


def create_app() -> FastAPI:
    """
    Application factory for the FastAPI backend.
    Later phases will register routers, middleware, and dependencies here.
    """
    app = FastAPI(
        title="Self-Correcting Multi-Agent AI System",
        version="0.1.0",
        description=(
            "Backend API for a multi-agent, self-correcting AI pipeline "
            "with claim-level verification and refinement."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[FRONTEND_ORIGIN],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(query_router)
    app.include_router(evaluations_router)

    @app.get("/health", tags=["system"])
    async def health_check() -> dict:
        return {"status": "ok"}

    return app


app = create_app()

