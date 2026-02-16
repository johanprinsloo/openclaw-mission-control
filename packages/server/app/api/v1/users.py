"""
User Management API endpoints.

GET    /api/v1/orgs/{orgSlug}/users              — List org members
POST   /api/v1/orgs/{orgSlug}/users              — Add a user (invite)
GET    /api/v1/orgs/{orgSlug}/users/{userId}      — Get user profile
PATCH  /api/v1/orgs/{orgSlug}/users/{userId}      — Update user
DELETE /api/v1/orgs/{orgSlug}/users/{userId}      — Remove user
POST   /api/v1/orgs/{orgSlug}/users/{userId}/rotate-key  — Rotate API key
POST   /api/v1/orgs/{orgSlug}/users/{userId}/revoke-key  — Revoke API key
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    AuthenticatedUser,
    get_authenticated_user,
    require_admin,
    require_member,
)
from app.core.database import get_session
from app.services import users as user_service
from openclaw_mc_shared.schemas.users import (
    ApiKeyRotateResponse,
    UserAddRequest,
    UserAddResponse,
    UserListResponse,
    UserResponse,
    UserUpdateRequest,
)

router = APIRouter()


@router.get("", response_model=UserListResponse, tags=["Users"])
async def list_users(
    auth: AuthenticatedUser = Depends(require_member),
    session: AsyncSession = Depends(get_session),
):
    """List all members of the org."""
    items = await user_service.list_org_users(auth.org_id, session)
    return UserListResponse(
        data=[UserResponse(**item) for item in items]
    )


@router.post("", response_model=UserAddResponse, status_code=201, tags=["Users"])
async def add_user(
    body: UserAddRequest,
    auth: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Add a user to the org (Admin only). For agents, the API key is returned once."""
    user_info, api_key = await user_service.add_user(auth.org_id, body, session)
    return UserAddResponse(
        user=UserResponse(**user_info),
        api_key=api_key,
    )


@router.get("/{userId}", response_model=UserResponse, tags=["Users"])
async def get_user(
    userId: uuid.UUID,
    auth: AuthenticatedUser = Depends(require_member),
    session: AsyncSession = Depends(get_session),
):
    """Get a user's profile within the org."""
    info = await user_service.get_user(auth.org_id, userId, session)
    return UserResponse(**info)


@router.patch("/{userId}", response_model=UserResponse, tags=["Users"])
async def update_user(
    userId: uuid.UUID,
    body: UserUpdateRequest,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    """Update user role (Admin) or display name (self or Admin)."""
    info = await user_service.update_user(
        auth.org_id,
        userId,
        body,
        caller_role=auth.role,
        caller_user_id=auth.user_id,
        session=session,
    )
    return UserResponse(**info)


@router.delete("/{userId}", status_code=204, tags=["Users"])
async def remove_user(
    userId: uuid.UUID,
    auth: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Remove a user from the org (Admin only). Immediately revokes access."""
    await user_service.remove_user(auth.org_id, userId, session)


@router.post(
    "/{userId}/rotate-key",
    response_model=ApiKeyRotateResponse,
    tags=["Users"],
)
async def rotate_api_key(
    userId: uuid.UUID,
    auth: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Rotate an agent's API key (Admin only). Old key valid for 24h grace period."""
    new_key, expires_at = await user_service.rotate_api_key(
        auth.org_id, userId, session
    )
    return ApiKeyRotateResponse(api_key=new_key, previous_key_expires_at=expires_at)


@router.post("/{userId}/revoke-key", status_code=204, tags=["Users"])
async def revoke_api_key(
    userId: uuid.UUID,
    auth: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Revoke an agent's API key immediately (Admin only)."""
    await user_service.revoke_api_key(auth.org_id, userId, session)
