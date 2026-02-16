"""
API v1 Router

All org-scoped endpoints are prefixed with /orgs/{orgSlug}.
"""

from fastapi import APIRouter
from . import projects, tasks, events, channels, users
from .organizations import router_global as orgs_global_router
from .organizations import router_scoped as orgs_scoped_router

router = APIRouter()

# Organization routes (non-org-scoped: list, create)
router.include_router(orgs_global_router)

# Organization routes (org-scoped: get, update, delete, reactivate)
router.include_router(orgs_scoped_router, prefix="/orgs/{orgSlug}", tags=["Organizations"])

# Include resource routers
# Note: Sub-agent POCs used {org_slug}, updating to {orgSlug} to match spec.
router.include_router(projects.router, prefix="/orgs/{orgSlug}/projects", tags=["Projects"])
router.include_router(tasks.router, prefix="/orgs/{orgSlug}/tasks", tags=["Tasks"])
router.include_router(events.router, prefix="/orgs/{orgSlug}/events", tags=["Events"])
router.include_router(channels.router, prefix="/orgs/{orgSlug}/channels", tags=["Channels"])
router.include_router(users.router, prefix="/orgs/{orgSlug}/users", tags=["Users"])


@router.get("/", tags=["API"])
async def api_root():
    """API root — returns version and available endpoints."""
    return {
        "api": "v1",
        "version": "0.1.0",
        "endpoints": [
            "/orgs",
            "/orgs/{orgSlug}/projects",
            "/orgs/{orgSlug}/tasks",
            "/orgs/{orgSlug}/channels",
            "/orgs/{orgSlug}/events",
            "/orgs/{orgSlug}/search",
        ],
    }
