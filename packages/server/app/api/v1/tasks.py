from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from app.core.database import get_session
from app.models.task import Task
from app.models.organization import Organization
from app.models.user import User
from app.core.auth import get_current_org, get_current_user
from openclaw_mc_shared.schemas.tasks import TaskRead, TaskCreate, TaskUpdate
import uuid

router = APIRouter()

@router.get("/", response_model=List[TaskRead])
async def list_tasks(
    org: Organization = Depends(get_current_org),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    page: int = 1,
    per_page: int = 25
):
    offset = (page - 1) * per_page
    statement = select(Task).where(Task.org_id == org.id).offset(offset).limit(per_page)
    result = await session.execute(statement)
    tasks = result.scalars().all()
    return tasks

@router.post("/", response_model=TaskRead)
async def create_task(
    task_in: TaskCreate,
    org: Organization = Depends(get_current_org),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    task = Task(**task_in.model_dump(), org_id=org.id)
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task

@router.get("/{task_id}", response_model=TaskRead)
async def get_task(
    task_id: uuid.UUID,
    org: Organization = Depends(get_current_org),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    task = await session.get(Task, task_id)
    if not task or task.org_id != org.id:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: uuid.UUID,
    task_in: TaskUpdate,
    org: Organization = Depends(get_current_org),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    task = await session.get(Task, task_id)
    if not task or task.org_id != org.id:
        raise HTTPException(status_code=404, detail="Task not found")
        
    task_data = task_in.model_dump(exclude_unset=True)
    for key, value in task_data.items():
        setattr(task, key, value)
        
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task

@router.delete("/{task_id}")
async def delete_task(
    task_id: uuid.UUID,
    org: Organization = Depends(get_current_org),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    task = await session.get(Task, task_id)
    if not task or task.org_id != org.id:
        raise HTTPException(status_code=404, detail="Task not found")
        
    await session.delete(task)
    await session.commit()
    return {"ok": True}
