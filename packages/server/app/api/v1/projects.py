from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from app.core.database import get_session
from app.models.project import Project
from app.models.organization import Organization
from app.models.user import User
from app.core.auth import get_current_org, get_current_user
from openclaw_mc_shared.schemas.projects import ProjectRead, ProjectCreate, ProjectUpdate
import uuid

router = APIRouter()

@router.get("/", response_model=List[ProjectRead])
async def list_projects(
    org: Organization = Depends(get_current_org),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    page: int = 1,
    per_page: int = 25
):
    offset = (page - 1) * per_page
    statement = select(Project).where(Project.org_id == org.id).offset(offset).limit(per_page)
    result = await session.execute(statement)
    projects = result.scalars().all()
    return projects

@router.post("/", response_model=ProjectRead)
async def create_project(
    project_in: ProjectCreate,
    org: Organization = Depends(get_current_org),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    project = Project(**project_in.model_dump(), org_id=org.id)
    if not project.owner_id:
        project.owner_id = user.id
        
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project

@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: uuid.UUID,
    org: Organization = Depends(get_current_org),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    project = await session.get(Project, project_id)
    if not project or project.org_id != org.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: uuid.UUID,
    project_in: ProjectUpdate,
    org: Organization = Depends(get_current_org),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    project = await session.get(Project, project_id)
    if not project or project.org_id != org.id:
        raise HTTPException(status_code=404, detail="Project not found")
        
    project_data = project_in.model_dump(exclude_unset=True)
    for key, value in project_data.items():
        setattr(project, key, value)
        
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project

@router.delete("/{project_id}")
async def delete_project(
    project_id: uuid.UUID,
    org: Organization = Depends(get_current_org),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    project = await session.get(Project, project_id)
    if not project or project.org_id != org.id:
        raise HTTPException(status_code=404, detail="Project not found")
        
    await session.delete(project)
    await session.commit()
    return {"ok": True}
