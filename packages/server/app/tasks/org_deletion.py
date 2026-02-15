"""
ARQ background task: finalize org deletions whose grace period has elapsed.

Scheduled to run periodically (e.g., every hour).
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from sqlmodel import select

from app.core.database import get_session_context
from app.models.organization import Organization
from app.services.organizations import finalize_org_deletion

log = structlog.get_logger()


async def finalize_pending_deletions(ctx: dict) -> int:
    """Check for orgs past their grace period and finalize deletion.

    Returns the number of orgs finalized.
    """
    now = datetime.now(timezone.utc)
    count = 0

    async with get_session_context() as session:
        result = await session.execute(
            select(Organization).where(
                Organization.status == "pending_deletion",
                Organization.deletion_scheduled_at <= now,
            )
        )
        orgs = result.scalars().all()

        for org in orgs:
            await finalize_org_deletion(org.id, session)
            count += 1

    if count:
        log.info("org_deletion.batch_finalized", count=count)
    return count


# ARQ worker settings
class WorkerSettings:
    """ARQ worker configuration."""

    functions = [finalize_pending_deletions]
    cron_jobs = [
        # Run every hour
        {
            "coroutine": finalize_pending_deletions,
            "hour": None,  # every hour
            "minute": 0,
        },
    ]
