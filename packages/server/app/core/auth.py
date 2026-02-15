from fastapi.security import APIKeyHeader
from fastapi import HTTPException, Security, Depends, WebSocket, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from typing import Optional
from app.core.database import get_session
from app.models.user_org import UserOrg
from app.models.organization import Organization
from app.models.user import User
import uuid

api_key_header = APIKeyHeader(name="Authorization", auto_error=False)

async def get_current_org(org_slug: str, session: AsyncSession = Depends(get_session)) -> Organization:
    # This dependency assumes org_slug is in path
    # For websocket, we might not use this directly in dependency chain if arguments differ
    result = await session.execute(select(Organization).where(Organization.slug == org_slug))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org

async def get_current_user(
    api_key: str = Security(api_key_header),
    org_slug: str = Depends(get_current_org), # Use org_slug to trigger get_current_org
    session: AsyncSession = Depends(get_session)
) -> User:
    # Note: org_slug param is actually the Organization object returned by get_current_org dependency
    org = org_slug 

    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API Key")

    token = api_key.replace("Bearer ", "").strip()
    
    try:
        user_id = uuid.UUID(token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid API Key format")

    stmt = select(UserOrg).where(
        UserOrg.user_id == user_id,
        UserOrg.org_id == org.id
    )
    result = await session.execute(stmt)
    user_org = result.scalar_one_or_none()
    
    if not user_org:
        raise HTTPException(status_code=403, detail="User not authorized for this organization")

    user_res = await session.execute(select(User).where(User.id == user_id))
    user = user_res.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
        
    return user

async def get_current_user_ws(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session)
) -> Optional[User]:
    if not token:
        return None
    
    try:
        # Assuming token is user_id for POC
        user_id = uuid.UUID(token)
        stmt = select(User).where(User.id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        return user
    except ValueError:
        return None
