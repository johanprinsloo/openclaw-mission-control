"""
Organization service — business logic for org CRUD and lifecycle.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import structlog
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.organization import Organization
from app.models.user_org import UserOrg

from openclaw_mc_shared.schemas.organizations import (
    OrgCreateRequest,
    OrgSettings,
    OrgStatus,
    OrgUpdateRequest,
    ORG_TRANSITIONS,
)

log = structlog.get_logger()


def _deep_merge(base: dict, patch: dict) -> dict:
    """JSON Merge Patch style deep merge."""
    result = base.copy()
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


async def list_user_orgs(
    user_id: uuid.UUID, session: AsyncSession
) -> list[dict]:
    """List all orgs a user belongs to, with their role."""
    result = await session.execute(
        select(Organization, UserOrg.role)
        .join(UserOrg, UserOrg.org_id == Organization.id)
        .where(UserOrg.user_id == user_id)
        .where(Organization.status != OrgStatus.DELETED.value)
    )
    rows = result.all()
    return [
        {
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "status": org.status,
            "role": role,
        }
        for org, role in rows
    ]


async def create_org(
    req: OrgCreateRequest,
    creator_id: uuid.UUID,
    creator_display_name: str,
    session: AsyncSession,
) -> Organization:
    """Create an org and make the creator an administrator."""
    # Check slug uniqueness
    existing = await session.execute(
        select(Organization).where(Organization.slug == req.slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Org slug already taken")

    org = Organization(
        name=req.name,
        slug=req.slug,
        status=OrgStatus.ACTIVE.value,
        settings=OrgSettings().model_dump(),
    )
    session.add(org)
    await session.flush()

    # Creator becomes admin
    membership = UserOrg(
        user_id=creator_id,
        org_id=org.id,
        role="administrator",
        display_name=creator_display_name,
    )
    session.add(membership)
    await session.flush()

    log.info("org.created", org_id=str(org.id), slug=req.slug, creator=str(creator_id))
    return org


async def get_org(org_slug: str, session: AsyncSession) -> Organization:
    """Get an org by slug; raises 404 if not found or deleted."""
    result = await session.execute(
        select(Organization).where(
            Organization.slug == org_slug,
            Organization.status != OrgStatus.DELETED.value,
        )
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


async def update_org(
    org: Organization,
    req: OrgUpdateRequest,
    session: AsyncSession,
) -> Organization:
    """Update org name and/or settings (deep merge)."""
    if org.status == OrgStatus.PENDING_DELETION.value:
        raise HTTPException(
            status_code=409,
            detail="Organization is pending deletion and read-only",
        )

    if req.name is not None:
        org.name = req.name

    if req.settings is not None:
        # Validate the merged result
        merged = _deep_merge(org.settings, req.settings)
        OrgSettings.model_validate(merged)  # raises ValidationError if invalid
        org.settings = merged

    org.updated_at = datetime.now(timezone.utc)
    session.add(org)
    await session.flush()

    log.info("org.updated", org_id=str(org.id), slug=org.slug)
    return org


async def begin_org_deletion(
    org: Organization, session: AsyncSession
) -> Organization:
    """Start the deletion grace period."""
    if org.status == OrgStatus.DELETED.value:
        raise HTTPException(status_code=404, detail="Organization not found")

    if org.status == OrgStatus.PENDING_DELETION.value:
        raise HTTPException(status_code=409, detail="Deletion already in progress")

    settings = OrgSettings.model_validate(org.settings)
    grace_days = settings.deletion_grace_period_days

    org.status = OrgStatus.PENDING_DELETION.value
    org.deletion_scheduled_at = datetime.now(timezone.utc) + timedelta(days=grace_days)
    org.updated_at = datetime.now(timezone.utc)
    session.add(org)
    await session.flush()

    log.info(
        "org.deletion_started",
        org_id=str(org.id),
        slug=org.slug,
        scheduled_at=str(org.deletion_scheduled_at),
    )
    return org


async def cancel_org_deletion(
    org: Organization, session: AsyncSession
) -> Organization:
    """Cancel a pending deletion, returning org to active."""
    if org.status != OrgStatus.PENDING_DELETION.value:
        raise HTTPException(
            status_code=409, detail="Org is not pending deletion"
        )

    org.status = OrgStatus.ACTIVE.value
    org.deletion_scheduled_at = None
    org.updated_at = datetime.now(timezone.utc)
    session.add(org)
    await session.flush()

    log.info("org.deletion_cancelled", org_id=str(org.id), slug=org.slug)
    return org


async def finalize_org_deletion(
    org_id: uuid.UUID, session: AsyncSession
) -> None:
    """Finalize deletion — called by ARQ background task after grace period."""
    result = await session.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = result.scalar_one_or_none()
    if not org:
        return

    if org.status != OrgStatus.PENDING_DELETION.value:
        log.info("org.deletion_skipped", org_id=str(org_id), status=org.status)
        return

    if org.deletion_scheduled_at and org.deletion_scheduled_at > datetime.now(timezone.utc):
        log.info("org.deletion_not_due", org_id=str(org_id))
        return

    org.status = OrgStatus.DELETED.value
    org.updated_at = datetime.now(timezone.utc)
    session.add(org)
    await session.flush()

    log.info("org.deleted", org_id=str(org_id), slug=org.slug)


async def suspend_org(
    org: Organization, session: AsyncSession
) -> Organization:
    """Suspend an org (admin action)."""
    current = OrgStatus(org.status)
    if OrgStatus.SUSPENDED not in ORG_TRANSITIONS.get(current, []):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot suspend org in state '{org.status}'",
        )
    org.status = OrgStatus.SUSPENDED.value
    org.updated_at = datetime.now(timezone.utc)
    session.add(org)
    await session.flush()
    log.info("org.suspended", org_id=str(org.id))
    return org


async def reactivate_org(
    org: Organization, session: AsyncSession
) -> Organization:
    """Reactivate a suspended org."""
    current = OrgStatus(org.status)
    if OrgStatus.ACTIVE not in ORG_TRANSITIONS.get(current, []):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot reactivate org in state '{org.status}'",
        )
    org.status = OrgStatus.ACTIVE.value
    org.deletion_scheduled_at = None
    org.updated_at = datetime.now(timezone.utc)
    session.add(org)
    await session.flush()
    log.info("org.reactivated", org_id=str(org.id))
    return org
