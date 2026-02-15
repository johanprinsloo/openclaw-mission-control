from typing import Optional, Any
from uuid import UUID

from fastapi import APIRouter, Request, Header, Depends, HTTPException, status
from sse_starlette.sse import EventSourceResponse
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.events import event_generator
from app.models.organization import Organization

router = APIRouter()

@router.get("/stream")
async def stream_events(
    request: Request,
    org_slug: str,
    last_event_id: Optional[int] = Header(None, alias="Last-Event-ID"),
    session: AsyncSession = Depends(get_session)
):
    """
    Stream events for an organization via SSE.
    """
    statement = select(Organization).where(Organization.slug == org_slug)
    result = await session.execute(statement)
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization '{org_slug}' not found"
        )
    
    return EventSourceResponse(
        event_generator(request, org.id, last_event_id)
    )
