"""
Mission Control API Server

Entry point for the FastAPI application.
"""

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.api.v1 import router as api_v1_router

settings = get_settings()
log = structlog.get_logger()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Mission Control",
        description="Coordination hub for OpenClaw agents and human teams.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes
    app.include_router(api_v1_router, prefix="/api/v1")

    @app.get("/health", tags=["System"])
    async def health_check():
        """Health check endpoint for liveness probes."""
        return {"status": "ok"}

    @app.get("/ready", tags=["System"])
    async def readiness_check():
        """Readiness check endpoint for startup probes."""
        # TODO: Verify DB and Redis connectivity
        return {"status": "ready"}

    @app.on_event("startup")
    async def on_startup():
        log.info("Mission Control starting", mode=settings.deployment_mode)

    @app.on_event("shutdown")
    async def on_shutdown():
        log.info("Mission Control shutting down")

    return app


app = create_app()
