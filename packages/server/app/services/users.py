"""
User management service — business logic for user CRUD, API key lifecycle.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.auth import generate_api_key, hash_api_key
from app.models.user import User
from app.models.user_org import UserOrg
from openclaw_mc_shared.schemas.users import (
    UserAddRequest,
    UserUpdateRequest,
    UserType,
)

log = structlog.get_logger()

API_KEY_GRACE_PERIOD_HOURS = 24


async def list_org_users(
    org_id: uuid.UUID, session: AsyncSession
) -> list[dict]:
    """List all users in an org with their membership info."""
    result = await session.execute(
        select(User, UserOrg)
        .join(UserOrg, UserOrg.user_id == User.id)
        .where(UserOrg.org_id == org_id)
    )
    rows = result.all()
    return [
        {
            "id": user.id,
            "type": user.type,
            "email": user.email,
            "identifier": user.identifier,
            "display_name": uo.display_name,
            "role": uo.role,
            "has_api_key": uo.api_key_hash is not None,
            "last_active": None,  # TODO: track last_active
            "created_at": user.created_at,
        }
        for user, uo in rows
    ]


async def add_user(
    org_id: uuid.UUID,
    req: UserAddRequest,
    session: AsyncSession,
) -> tuple[dict, Optional[str]]:
    """Add a user to the org. Returns (user_info, plaintext_api_key_or_none)."""
    # Validate request
    if req.type == UserType.HUMAN and not req.email:
        raise HTTPException(status_code=422, detail="Email is required for human users")
    if req.type == UserType.AGENT and not req.identifier:
        raise HTTPException(status_code=422, detail="Identifier is required for agent users")

    # Check for existing user
    user: Optional[User] = None
    if req.type == UserType.HUMAN and req.email:
        result = await session.execute(
            select(User).where(User.email == req.email)
        )
        user = result.scalar_one_or_none()
    elif req.type == UserType.AGENT and req.identifier:
        result = await session.execute(
            select(User).where(
                User.type == "agent", User.identifier == req.identifier
            )
        )
        user = result.scalar_one_or_none()

    if user:
        # Check if already a member
        result = await session.execute(
            select(UserOrg).where(
                UserOrg.user_id == user.id, UserOrg.org_id == org_id
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="User is already a member of this org")
    else:
        # Create new user
        user = User(
            email=req.email if req.type == UserType.HUMAN else None,
            type=req.type.value,
            identifier=req.identifier if req.type == UserType.AGENT else None,
        )
        session.add(user)
        await session.flush()

    # Generate API key for agents
    plaintext_key: Optional[str] = None
    api_key_hash_val: Optional[str] = None
    if req.type == UserType.AGENT:
        plaintext_key = generate_api_key(user.id)
        api_key_hash_val = hash_api_key(plaintext_key)

    # Create membership
    membership = UserOrg(
        user_id=user.id,
        org_id=org_id,
        role=req.role.value,
        display_name=req.display_name,
        api_key_hash=api_key_hash_val,
    )
    session.add(membership)
    await session.flush()

    log.info(
        "user.added",
        user_id=str(user.id),
        org_id=str(org_id),
        type=req.type.value,
        role=req.role.value,
    )

    user_info = {
        "id": user.id,
        "type": user.type,
        "email": user.email,
        "identifier": user.identifier,
        "display_name": membership.display_name,
        "role": membership.role,
        "has_api_key": api_key_hash_val is not None,
        "last_active": None,
        "created_at": user.created_at,
    }
    return user_info, plaintext_key


async def get_user(
    org_id: uuid.UUID, user_id: uuid.UUID, session: AsyncSession
) -> dict:
    """Get a single user's info within the org."""
    result = await session.execute(
        select(User, UserOrg)
        .join(UserOrg, UserOrg.user_id == User.id)
        .where(UserOrg.org_id == org_id, UserOrg.user_id == user_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="User not found in this org")
    user, uo = row
    return {
        "id": user.id,
        "type": user.type,
        "email": user.email,
        "identifier": user.identifier,
        "display_name": uo.display_name,
        "role": uo.role,
        "has_api_key": uo.api_key_hash is not None,
        "last_active": None,
        "created_at": user.created_at,
    }


async def update_user(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    req: UserUpdateRequest,
    caller_role: str,
    caller_user_id: uuid.UUID,
    session: AsyncSession,
) -> dict:
    """Update a user's role or display name."""
    result = await session.execute(
        select(UserOrg).where(
            UserOrg.org_id == org_id, UserOrg.user_id == user_id
        )
    )
    uo = result.scalar_one_or_none()
    if not uo:
        raise HTTPException(status_code=404, detail="User not found in this org")

    # Role changes require admin
    if req.role is not None:
        if caller_role != "administrator":
            raise HTTPException(status_code=403, detail="Only admins can change roles")
        uo.role = req.role.value

    # Display name: self or admin
    if req.display_name is not None:
        if caller_user_id != user_id and caller_role != "administrator":
            raise HTTPException(
                status_code=403,
                detail="Only the user or an admin can change display name",
            )
        uo.display_name = req.display_name

    session.add(uo)
    await session.flush()

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()

    log.info("user.updated", user_id=str(user_id), org_id=str(org_id))
    return {
        "id": user.id,
        "type": user.type,
        "email": user.email,
        "identifier": user.identifier,
        "display_name": uo.display_name,
        "role": uo.role,
        "has_api_key": uo.api_key_hash is not None,
        "last_active": None,
        "created_at": user.created_at,
    }


async def remove_user(
    org_id: uuid.UUID, user_id: uuid.UUID, session: AsyncSession
) -> None:
    """Remove a user from the org. Immediately revokes access."""
    result = await session.execute(
        select(UserOrg).where(
            UserOrg.org_id == org_id, UserOrg.user_id == user_id
        )
    )
    uo = result.scalar_one_or_none()
    if not uo:
        raise HTTPException(status_code=404, detail="User not found in this org")

    await session.delete(uo)
    await session.flush()
    log.info("user.removed", user_id=str(user_id), org_id=str(org_id))


async def rotate_api_key(
    org_id: uuid.UUID, user_id: uuid.UUID, session: AsyncSession
) -> tuple[str, datetime]:
    """Rotate an agent's API key. Returns (new_plaintext_key, previous_expires_at)."""
    result = await session.execute(
        select(UserOrg, User)
        .join(User, User.id == UserOrg.user_id)
        .where(UserOrg.org_id == org_id, UserOrg.user_id == user_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="User not found in this org")

    uo, user = row
    if user.type != "agent":
        raise HTTPException(status_code=400, detail="API key rotation is only for agent users")

    # Move current key to previous with grace period
    expires_at = datetime.now(timezone.utc) + timedelta(hours=API_KEY_GRACE_PERIOD_HOURS)
    uo.api_key_previous_hash = uo.api_key_hash
    uo.api_key_previous_expires_at = expires_at.isoformat()

    # Generate new key
    new_key = generate_api_key(user.id)
    uo.api_key_hash = hash_api_key(new_key)

    session.add(uo)
    await session.flush()

    log.info("api_key.rotated", user_id=str(user_id), org_id=str(org_id))
    return new_key, expires_at


async def revoke_api_key(
    org_id: uuid.UUID, user_id: uuid.UUID, session: AsyncSession
) -> None:
    """Revoke an agent's API key immediately (no grace period)."""
    result = await session.execute(
        select(UserOrg, User)
        .join(User, User.id == UserOrg.user_id)
        .where(UserOrg.org_id == org_id, UserOrg.user_id == user_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="User not found in this org")

    uo, user = row
    if user.type != "agent":
        raise HTTPException(status_code=400, detail="API key revocation is only for agent users")

    uo.api_key_hash = None
    uo.api_key_previous_hash = None
    uo.api_key_previous_expires_at = None

    session.add(uo)
    await session.flush()
    log.info("api_key.revoked", user_id=str(user_id), org_id=str(org_id))
