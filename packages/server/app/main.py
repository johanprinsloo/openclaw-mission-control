"""
Mission Control API Server

Entry point for the FastAPI application.
"""

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.middleware import CSRFMiddleware, SecurityHeadersMiddleware
from app.core.redis import close_redis
from app.api.v1 import router as api_v1_router
from app.api.v1.auth import router as auth_router

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

    # Middleware (order matters — outermost first)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
    )

    # Auth routes (not org-scoped)
    app.include_router(auth_router, prefix="/auth", tags=["Authentication"])

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
        await close_redis()

    # Serve frontend SPA
    import os
    from fastapi import Request
    from fastapi.responses import FileResponse
    from starlette.exceptions import HTTPException as StarletteHTTPException

    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    frontend_dist = os.path.join(root_dir, "frontend", "dist")

    if os.path.exists(frontend_dist):
        @app.get("/{catchall:path}", tags=["Frontend"], include_in_schema=False)
        async def serve_spa(request: Request, catchall: str):
            # Do not intercept API, auth, or doc routes
            if catchall.startswith("api/") or catchall.startswith("auth/") or catchall.startswith("docs") or catchall.startswith("openapi.json"):
                raise StarletteHTTPException(status_code=404, detail="Not Found")
            
            # Serve specific files (assets, vite.svg, etc) if they exist
            if catchall:
                file_path = os.path.join(frontend_dist, catchall)
                if os.path.isfile(file_path):
                    return FileResponse(file_path)
            
            # Serve index.html for SPA routes (e.g. /orgs)
            index_path = os.path.join(frontend_dist, "index.html")
            if os.path.isfile(index_path):
                return FileResponse(index_path)
            
            raise StarletteHTTPException(status_code=404, detail="Not Found")

    return app


app = create_app()
