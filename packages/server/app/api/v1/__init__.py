"""
API v1 Router

All org-scoped endpoints are prefixed with /orgs/{orgSlug}.
"""

from fastapi import APIRouter

router = APIRouter()


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
