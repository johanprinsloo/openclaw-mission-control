"""
Organization API endpoints.

GET    /api/v1/orgs              — List orgs for authenticated user
POST   /api/v1/orgs              — Create a new org
GET    /api/v1/orgs/{orgSlug}    — Get org details
PATCH  /api/v1/orgs/{orgSlug}    — Update org name/settings
DELETE /api/v1/orgs/{orgSlug}    — Begin org deletion grace period
POST   /api/v1/orgs/{orgSlug}/reactivate — Cancel deletion / reactivate
"""

from __future__ import annotations

import uuid
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Cookie
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    AuthenticatedUser,
    decode_jwt,
    get_authenticated_user,
    require_admin,
)
from app.core.database import get_session
from app.models.user import User
from app.services import organizations as org_service
from openclaw_mc_shared.schemas.organizations import (
    OrgCreateRequest,
    OrgListResponse,
    OrgResponse,
    OrgSettings,
    OrgUpdateRequest,
)

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Non-org-scoped routes (no orgSlug in path)
# ---------------------------------------------------------------------------
router_global = APIRouter()


@router_global.get("/orgs", response_model=OrgListResponse, tags=["Organizations"])
async def list_orgs(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """List orgs the authenticated user belongs to."""
    user_id = await _get_user_id_from_request(request, session)
    items = await org_service.list_user_orgs(user_id, session)
    return OrgListResponse(data=items)


@router_global.post("/orgs", response_model=OrgResponse, status_code=201, tags=["Organizations"])
async def create_org(
    body: OrgCreateRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Create a new organization. The creator becomes an administrator."""
    user_id = await _get_user_id_from_request(request, session)
    # Get user for display name
    from sqlmodel import select
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    display_name = user.email or user.identifier or "Admin"
    org = await org_service.create_org(body, user_id, display_name, session)
    settings = OrgSettings.model_validate(org.settings)
    return OrgResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        status=org.status,
        settings=settings,
        created_at=org.created_at,
        updated_at=org.updated_at,
        deletion_scheduled_at=org.deletion_scheduled_at,
    )


# ---------------------------------------------------------------------------
# Org-scoped routes (orgSlug in path)
# ---------------------------------------------------------------------------
router_scoped = APIRouter()


@router_scoped.get("", response_model=OrgResponse, tags=["Organizations"])
async def get_org(
    auth: AuthenticatedUser = Depends(get_authenticated_user),
):
    """Get org details including settings."""
    org = auth.org
    settings = OrgSettings.model_validate(org.settings)
    return OrgResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        status=org.status,
        settings=settings,
        created_at=org.created_at,
        updated_at=org.updated_at,
        deletion_scheduled_at=org.deletion_scheduled_at,
    )


@router_scoped.patch("", response_model=OrgResponse, tags=["Organizations"])
async def update_org(
    body: OrgUpdateRequest,
    auth: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Update org name or settings (Admin only). Settings are deep-merged."""
    org = await org_service.update_org(auth.org, body, session)
    settings = OrgSettings.model_validate(org.settings)
    return OrgResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        status=org.status,
        settings=settings,
        created_at=org.created_at,
        updated_at=org.updated_at,
        deletion_scheduled_at=org.deletion_scheduled_at,
    )


@router_scoped.delete("", status_code=202, tags=["Organizations"])
async def delete_org(
    auth: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Begin org deletion grace period (Admin only)."""
    org = await org_service.begin_org_deletion(auth.org, session)
    return {
        "message": "Org deletion initiated",
        "deletion_scheduled_at": str(org.deletion_scheduled_at),
    }


@router_scoped.post("/reactivate", response_model=OrgResponse, tags=["Organizations"])
async def reactivate_org(
    auth: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Cancel pending deletion or reactivate a suspended org (Admin only)."""
    org = auth.org
    if org.status == "pending_deletion":
        org = await org_service.cancel_org_deletion(org, session)
    elif org.status == "suspended":
        org = await org_service.reactivate_org(org, session)
    else:
        raise HTTPException(status_code=409, detail="Org is already active")

    settings = OrgSettings.model_validate(org.settings)
    return OrgResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        status=org.status,
        settings=settings,
        created_at=org.created_at,
        updated_at=org.updated_at,
        deletion_scheduled_at=org.deletion_scheduled_at,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_user_id_from_request(
    request: Request, session: AsyncSession
) -> uuid.UUID:
    """Extract user ID from JWT cookie or API key header (non-org-scoped)."""
    # Try JWT cookie
    token = request.cookies.get("mc_session")
    if token:
        try:
            payload = decode_jwt(token)
            return uuid.UUID(payload["sub"])
        except Exception:
            pass

    # Try Authorization header (Bearer token — could be API key or UUID)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token_val = auth_header[7:].strip()
        # Try as UUID (POC compat)
        try:
            return uuid.UUID(token_val)
        except ValueError:
            pass

    raise HTTPException(status_code=401, detail="Authentication required")
