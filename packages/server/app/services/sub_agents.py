"""Sub-agent management service — business logic for spawning, lifecycle, and termination."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.auth import generate_api_key, hash_api_key
from app.models.sub_agent import SubAgent
from openclaw_mc_shared.schemas.sub_agents import SubAgentCreate

log = structlog.get_logger()


async def spawn_sub_agent(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    req: SubAgentCreate,
    session: AsyncSession,
) -> tuple[SubAgent, str]:
    """Spawn a new sub-agent with an ephemeral API key."""
    # Create the sub-agent record
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=req.timeout_minutes)
    
    sub_agent = SubAgent(
        org_id=org_id,
        task_id=req.task_id,
        model=req.model,
        instructions=req.instructions,
        status="active",
        created_by=user_id,
        expires_at=expires_at,
    )
    
    # Generate ephemeral API key
    plaintext_key = generate_api_key(sub_agent.id, temporary=True)
    sub_agent.api_key_hash = hash_api_key(plaintext_key)
    
    session.add(sub_agent)
    await session.flush()
    
    log.info(
        "sub_agent.spawned",
        sub_agent_id=str(sub_agent.id),
        org_id=str(org_id),
        task_id=str(req.task_id),
        model=req.model,
    )
    
    return sub_agent, plaintext_key


async def list_sub_agents(
    org_id: uuid.UUID, 
    session: AsyncSession,
    status: Optional[str] = None
) -> list[SubAgent]:
    """List sub-agents for an org, optionally filtered by status."""
    stmt = select(SubAgent).where(SubAgent.org_id == org_id)
    if status:
        stmt = stmt.where(SubAgent.status == status)
    
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_sub_agent_or_404(
    org_id: uuid.UUID, 
    sub_agent_id: uuid.UUID, 
    session: AsyncSession
) -> SubAgent:
    """Get a sub-agent by ID or raise 404."""
    result = await session.execute(
        select(SubAgent).where(
            SubAgent.org_id == org_id, 
            SubAgent.id == sub_agent_id
        )
    )
    sub_agent = result.scalar_one_or_none()
    if not sub_agent:
        raise HTTPException(status_code=404, detail="Sub-agent not found")
    return sub_agent


async def terminate_sub_agent(
    org_id: uuid.UUID,
    sub_agent_id: uuid.UUID,
    reason: Optional[str],
    session: AsyncSession,
) -> SubAgent:
    """Terminate a sub-agent immediately."""
    sub_agent = await get_sub_agent_or_404(org_id, sub_agent_id, session)
    
    if sub_agent.status == "terminated":
        return sub_agent
        
    sub_agent.status = "terminated"
    sub_agent.terminated_at = datetime.now(timezone.utc)
    sub_agent.termination_reason = reason
    
    session.add(sub_agent)
    await session.flush()
    
    log.info(
        "sub_agent.terminated",
        sub_agent_id=str(sub_agent_id),
        org_id=str(org_id),
        reason=reason,
    )
    
    return sub_agent
