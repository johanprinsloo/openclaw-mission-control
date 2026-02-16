"""
Task endpoints: CRUD, transitions, dependencies, evidence.

Status columns: Backlog → In Progress → In Review → Complete
- Evidence gate: transitioning to Complete requires all required_evidence_types submitted.
- Dependencies: blocked tasks cannot be completed until blockers are complete.
- Circular dependency detection on add.
- SSE events emitted on create, update, transition.
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.auth import AuthenticatedUser, require_contributor, require_member
from app.core.database import get_session
from app.core.events import broadcast_event
from app.models.assignments import TaskProjectAssignment, TaskUserAssignment
from app.models.task import Task
from app.services.tasks import (
    add_dependency,
    create_task,
    enrich_task,
    enrich_tasks,
    get_task_or_404,
    remove_dependency,
    transition_task,
    update_task,
)
from openclaw_mc_shared.schemas.common import TaskPriority, TaskStatus
from openclaw_mc_shared.schemas.tasks import (
    DependencyAdd,
    DependencyRead,
    TaskCreate,
    TaskRead,
    TaskTransition,
    TaskUpdate,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Task CRUD
# ---------------------------------------------------------------------------


@router.get("/", response_model=List[TaskRead])
async def list_tasks_endpoint(
    orgSlug: str,
    project_id: Optional[uuid.UUID] = None,
    status: Optional[TaskStatus] = None,
    assignee_id: Optional[uuid.UUID] = None,
    priority: Optional[TaskPriority] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    auth: AuthenticatedUser = Depends(require_member),
    session: AsyncSession = Depends(get_session),
):
    """List tasks with optional filters by project, status, assignee, priority."""
    stmt = select(Task).where(Task.org_id == auth.org_id)

    if status:
        stmt = stmt.where(Task.status == status.value)
    if priority:
        stmt = stmt.where(Task.priority == priority.value)

    # Filter by project (join through assignment table)
    if project_id:
        stmt = stmt.join(
            TaskProjectAssignment,
            TaskProjectAssignment.task_id == Task.id,
        ).where(TaskProjectAssignment.project_id == project_id)

    # Filter by assignee (join through assignment table)
    if assignee_id:
        stmt = stmt.join(
            TaskUserAssignment,
            TaskUserAssignment.task_id == Task.id,
        ).where(TaskUserAssignment.user_id == assignee_id)

    stmt = stmt.distinct().offset((page - 1) * per_page).limit(per_page)
    result = await session.execute(stmt)
    tasks = list(result.scalars().all())
    return await enrich_tasks(session, tasks)


@router.post("/", response_model=TaskRead, status_code=201)
async def create_task_endpoint(
    orgSlug: str,
    task_in: TaskCreate,
    auth: AuthenticatedUser = Depends(require_contributor),
    session: AsyncSession = Depends(get_session),
):
    """Create a new task."""
    task = await create_task(session, task_in, auth.org_id)
    await session.commit()
    await session.refresh(task)

    enriched = await enrich_task(session, task)

    await broadcast_event(
        session=session,
        org_id=auth.org_id,
        event_type="task.created",
        payload={
            "task_id": str(task.id),
            "title": task.title,
            "status": task.status,
            "priority": task.priority,
            "project_ids": [str(p) for p in enriched.project_ids],
            "assignee_ids": [str(a) for a in enriched.assignee_ids],
        },
        actor_id=auth.user_id,
        actor_type="human",
    )

    return enriched


@router.get("/{task_id}", response_model=TaskRead)
async def get_task_endpoint(
    orgSlug: str,
    task_id: uuid.UUID,
    auth: AuthenticatedUser = Depends(require_member),
    session: AsyncSession = Depends(get_session),
):
    """Get a single task with full details."""
    task = await get_task_or_404(session, task_id, auth.org_id)
    return await enrich_task(session, task)


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task_endpoint(
    orgSlug: str,
    task_id: uuid.UUID,
    task_in: TaskUpdate,
    auth: AuthenticatedUser = Depends(require_contributor),
    session: AsyncSession = Depends(get_session),
):
    """Update task metadata."""
    task = await get_task_or_404(session, task_id, auth.org_id)
    task = await update_task(session, task, task_in, auth.org_id)
    await session.commit()
    await session.refresh(task)

    enriched = await enrich_task(session, task)

    await broadcast_event(
        session=session,
        org_id=auth.org_id,
        event_type="task.updated",
        payload={
            "task_id": str(task.id),
            **task_in.model_dump(exclude_unset=True, mode="json"),
        },
        actor_id=auth.user_id,
        actor_type="human",
    )

    return enriched


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------


@router.post("/{task_id}/transition", response_model=TaskRead)
async def transition_task_endpoint(
    orgSlug: str,
    task_id: uuid.UUID,
    body: TaskTransition,
    auth: AuthenticatedUser = Depends(require_contributor),
    session: AsyncSession = Depends(get_session),
):
    """Transition a task to a new status. Evidence gate enforced for completion."""
    task = await get_task_or_404(session, task_id, auth.org_id)
    old_status = task.status

    task = await transition_task(
        session, task, body.to_status, body.evidence, auth.user_id, auth.org_id
    )
    await session.commit()
    await session.refresh(task)

    enriched = await enrich_task(session, task)

    await broadcast_event(
        session=session,
        org_id=auth.org_id,
        event_type="task.transitioned",
        payload={
            "task_id": str(task.id),
            "from_status": old_status,
            "to_status": body.to_status.value,
            "title": task.title,
        },
        actor_id=auth.user_id,
        actor_type="human",
    )

    return enriched


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


@router.post("/{task_id}/dependencies", status_code=201)
async def add_dependency_endpoint(
    orgSlug: str,
    task_id: uuid.UUID,
    body: DependencyAdd,
    auth: AuthenticatedUser = Depends(require_contributor),
    session: AsyncSession = Depends(get_session),
):
    """Add a dependency (task is blocked by blocked_by_id). Detects circular deps."""
    await add_dependency(session, task_id, body.blocked_by_id, auth.org_id)
    await session.commit()

    await broadcast_event(
        session=session,
        org_id=auth.org_id,
        event_type="task.dependency.added",
        payload={
            "task_id": str(task_id),
            "blocked_by_id": str(body.blocked_by_id),
        },
        actor_id=auth.user_id,
        actor_type="human",
    )

    return {"ok": True}


@router.delete("/{task_id}/dependencies/{blocked_by_id}")
async def remove_dependency_endpoint(
    orgSlug: str,
    task_id: uuid.UUID,
    blocked_by_id: uuid.UUID,
    auth: AuthenticatedUser = Depends(require_contributor),
    session: AsyncSession = Depends(get_session),
):
    """Remove a dependency."""
    await remove_dependency(session, task_id, blocked_by_id, auth.org_id)
    await session.commit()

    await broadcast_event(
        session=session,
        org_id=auth.org_id,
        event_type="task.dependency.removed",
        payload={
            "task_id": str(task_id),
            "blocked_by_id": str(blocked_by_id),
        },
        actor_id=auth.user_id,
        actor_type="human",
    )

    return {"ok": True}
