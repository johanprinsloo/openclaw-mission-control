from fastapi.security import APIKeyHeader
from fastapi import HTTPException, Security, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from app.core.database import get_session
from app.models.user_org import UserOrg
from app.models.organization import Organization
from app.models.user import User
import uuid

api_key_header = APIKeyHeader(name="Authorization", auto_error=False)

async def get_current_org(org_slug: str, session: AsyncSession = Depends(get_session)) -> Organization:
    result = await session.execute(select(Organization).where(Organization.slug == org_slug))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org

async def get_current_user(
    api_key: str = Security(api_key_header),
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_session)
) -> User:
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
