"""
API v1 Router

All org-scoped endpoints are prefixed with /orgs/{orgSlug}.
"""

from fastapi import APIRouter
from . import projects, tasks, events, channels

router = APIRouter()

# Include resource routers
# Note: Sub-agent POCs used {org_slug}, updating to {orgSlug} to match spec.
router.include_router(projects.router, prefix="/orgs/{orgSlug}/projects", tags=["Projects"])
router.include_router(tasks.router, prefix="/orgs/{orgSlug}/tasks", tags=["Tasks"])
router.include_router(events.router, prefix="/orgs/{orgSlug}/events", tags=["Events"])
router.include_router(channels.router, prefix="/orgs/{orgSlug}/channels", tags=["Channels"])


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
