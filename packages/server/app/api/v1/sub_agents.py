"""Sub-agent API endpoints: spawn, list, get, terminate."""

from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser, require_contributor, require_member
from app.core.database import get_session
from app.core.events import broadcast_event
from app.services.sub_agents import (
    spawn_sub_agent,
    list_sub_agents,
    get_sub_agent_or_404,
    terminate_sub_agent,
)
from openclaw_mc_shared.schemas.sub_agents import (
    SubAgentCreate,
    SubAgentRead,
    SubAgentSpawnResponse,
    SubAgentTerminateRequest,
)

router = APIRouter()


@router.get("/", response_model=List[SubAgentRead])
async def list_sub_agents_endpoint(
    orgSlug: str,
    status: Optional[str] = Query(None, pattern="^(active|terminated)$"),
    auth: AuthenticatedUser = Depends(require_member),
    session: AsyncSession = Depends(get_session),
):
    """List sub-agents for an organization."""
    return await list_sub_agents(auth.org_id, session, status)


@router.post("/", response_model=SubAgentSpawnResponse, status_code=201)
async def spawn_sub_agent_endpoint(
    orgSlug: str,
    req: SubAgentCreate,
    auth: AuthenticatedUser = Depends(require_contributor),
    session: AsyncSession = Depends(get_session),
):
    """Spawn a new sub-agent for a task. Returns ephemeral API key once."""
    sub_agent, plaintext_key = await spawn_sub_agent(
        auth.org_id, auth.user_id, req, session
    )
    await session.commit()
    await session.refresh(sub_agent)

    await broadcast_event(
        session=session,
        org_id=auth.org_id,
        event_type="sub_agent.spawned",
        payload={
            "sub_agent_id": str(sub_agent.id),
            "task_id": str(sub_agent.task_id),
            "model": sub_agent.model,
        },
        actor_id=auth.user_id,
        actor_type="human",
    )

    return SubAgentSpawnResponse(sub_agent=sub_agent, api_key=plaintext_key)


@router.get("/{sub_agent_id}", response_model=SubAgentRead)
async def get_sub_agent_endpoint(
    orgSlug: str,
    sub_agent_id: uuid.UUID,
    auth: AuthenticatedUser = Depends(require_member),
    session: AsyncSession = Depends(get_session),
):
    """Get sub-agent details and status."""
    return await get_sub_agent_or_404(auth.org_id, sub_agent_id, session)


@router.post("/{sub_agent_id}/terminate", response_model=SubAgentRead)
async def terminate_sub_agent_endpoint(
    orgSlug: str,
    sub_agent_id: uuid.UUID,
    req: SubAgentTerminateRequest,
    auth: AuthenticatedUser = Depends(require_contributor),
    session: AsyncSession = Depends(get_session),
):
    """Terminate a sub-agent immediately, revoking its API key."""
    sub_agent = await terminate_sub_agent(
        auth.org_id, sub_agent_id, req.reason, session
    )
    await session.commit()
    await session.refresh(sub_agent)

    await broadcast_event(
        session=session,
        org_id=auth.org_id,
        event_type="sub_agent.terminated",
        payload={
            "sub_agent_id": str(sub_agent.id),
            "task_id": str(sub_agent.task_id),
            "reason": req.reason,
        },
        actor_id=auth.user_id,
        actor_type="human",
    )

    return sub_agent
