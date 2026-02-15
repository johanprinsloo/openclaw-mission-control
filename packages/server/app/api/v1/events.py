"""
SSE Event Streaming endpoints.

- GET /stream — Authenticated SSE stream with subscription filtering and replay
- GET /subscriptions — Get user's event subscriptions
- PUT /subscriptions — Update user's event subscriptions
"""

from __future__ import annotations

import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sse_starlette.sse import EventSourceResponse

from app.core.auth import AuthenticatedUser, require_member
from app.core.database import get_session
from app.core.events import event_generator, get_sse_connection_count, MAX_CONNECTIONS_PER_ORG
from app.models.subscription import Subscription

router = APIRouter()


# --- Schemas ---


class SubscriptionItem(BaseModel):
    topic_type: str  # project | task | channel | event_type
    topic_id: str


class SubscriptionList(BaseModel):
    subscriptions: list[SubscriptionItem]


# --- SSE Stream ---


@router.get("/stream")
async def stream_events(
    request: Request,
    orgSlug: str,
    last_event_id: Optional[int] = Header(None, alias="Last-Event-ID"),
    auth: AuthenticatedUser = Depends(require_member),
    session: AsyncSession = Depends(get_session),
):
    """
    Stream events for an organization via SSE.

    Authenticated via JWT cookie or API key. Events are filtered by the
    user's subscriptions. Supports cursor-based replay via Last-Event-ID header.

    If the cursor is too old, an `events.reset` event is sent to signal
    the client should perform a full data refresh.

    Emits `: heartbeat` comments every 30 seconds to keep the connection alive.
    """
    # Check connection limit before starting stream
    current_count = await get_sse_connection_count(auth.org_id)
    if current_count >= MAX_CONNECTIONS_PER_ORG:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many concurrent SSE connections for this organization.",
        )

    # Load user subscriptions
    stmt = select(Subscription).where(
        Subscription.user_id == auth.user_id,
        Subscription.org_id == auth.org_id,
    )
    result = await session.execute(stmt)
    subs = result.scalars().all()

    subscriptions = (
        [{"topic_type": s.topic_type, "topic_id": str(s.topic_id)} for s in subs]
        if subs
        else None  # None = no filter, receive all
    )

    # Extract JTI for revocation checking
    jti = None
    if hasattr(request.state, "auth"):
        # JTI was stored during auth if JWT-based
        jti = getattr(request.state, "jti", None)

    return EventSourceResponse(
        event_generator(
            request,
            auth.org_id,
            last_event_id=last_event_id,
            subscriptions=subscriptions,
            jti=jti,
        )
    )


# --- Subscription Management ---


@router.get(
    "/subscriptions",
    response_model=SubscriptionList,
    summary="Get event subscriptions",
)
async def get_subscriptions(
    orgSlug: str,
    auth: AuthenticatedUser = Depends(require_member),
    session: AsyncSession = Depends(get_session),
):
    """Get the current user's event subscription filters for this org."""
    stmt = select(Subscription).where(
        Subscription.user_id == auth.user_id,
        Subscription.org_id == auth.org_id,
    )
    result = await session.execute(stmt)
    subs = result.scalars().all()

    return SubscriptionList(
        subscriptions=[
            SubscriptionItem(topic_type=s.topic_type, topic_id=str(s.topic_id))
            for s in subs
        ]
    )


@router.put(
    "/subscriptions",
    response_model=SubscriptionList,
    summary="Update event subscriptions",
)
async def update_subscriptions(
    orgSlug: str,
    body: SubscriptionList,
    auth: AuthenticatedUser = Depends(require_member),
    session: AsyncSession = Depends(get_session),
):
    """
    Replace the user's event subscriptions for this org.

    This is a full replacement — all existing subscriptions are deleted
    and replaced with the provided list.
    """
    # Delete existing subscriptions
    stmt = select(Subscription).where(
        Subscription.user_id == auth.user_id,
        Subscription.org_id == auth.org_id,
    )
    result = await session.execute(stmt)
    existing = result.scalars().all()
    for sub in existing:
        await session.delete(sub)

    # Create new subscriptions
    new_subs = []
    for item in body.subscriptions:
        sub = Subscription(
            user_id=auth.user_id,
            org_id=auth.org_id,
            topic_type=item.topic_type,
            topic_id=UUID(item.topic_id),
        )
        session.add(sub)
        new_subs.append(item)

    await session.commit()

    return SubscriptionList(subscriptions=new_subs)
