"""
Project endpoints: CRUD, lifecycle transitions, membership.

Lifecycle stages (ordered): Definition → POC → Development → Testing → Launch → Maintenance
- Forward: one step at a time
- Backward: any earlier stage allowed
- Auto-creates a default project channel on creation
- Emits SSE events on transition
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.auth import (
    AuthenticatedUser,
    require_admin,
    require_contributor,
    require_member,
)
from app.core.database import get_session
from app.core.events import broadcast_event
from app.models.assignments import ProjectUserAssignment, TaskProjectAssignment
from app.models.channel import Channel
from app.models.project import Project
from app.models.task import Task
from app.models.user import User
from openclaw_mc_shared.schemas.common import ProjectStage
from openclaw_mc_shared.schemas.projects import (
    ProjectCreate,
    ProjectMemberAdd,
    ProjectMemberRead,
    ProjectRead,
    ProjectTransition,
    ProjectUpdate,
    validate_transition,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_project_or_404(
    session: AsyncSession, project_id: uuid.UUID, org_id: uuid.UUID
) -> Project:
    project = await session.get(Project, project_id)
    if not project or project.org_id != org_id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _enrich_task_counts(
    session: AsyncSession, projects: list[Project]
) -> list[dict]:
    """Add task_count and task_complete_count to project dicts."""
    if not projects:
        return []

    project_ids = [p.id for p in projects]

    # Total tasks per project (via join table)
    total_stmt = (
        select(
            TaskProjectAssignment.project_id,
            func.count().label("cnt"),
        )
        .where(TaskProjectAssignment.project_id.in_(project_ids))
        .group_by(TaskProjectAssignment.project_id)
    )
    total_result = await session.execute(total_stmt)
    totals = {row.project_id: row.cnt for row in total_result}

    # Complete tasks per project
    complete_stmt = (
        select(
            TaskProjectAssignment.project_id,
            func.count().label("cnt"),
        )
        .join(Task, Task.id == TaskProjectAssignment.task_id)
        .where(
            TaskProjectAssignment.project_id.in_(project_ids),
            Task.status == "complete",
        )
        .group_by(TaskProjectAssignment.project_id)
    )
    complete_result = await session.execute(complete_stmt)
    completes = {row.project_id: row.cnt for row in complete_result}

    results = []
    for p in projects:
        d = {
            "id": p.id,
            "org_id": p.org_id,
            "name": p.name,
            "type": p.type,
            "description": p.description,
            "stage": p.stage,
            "owner_id": p.owner_id,
            "links": p.links or {},
            "task_count": totals.get(p.id, 0),
            "task_complete_count": completes.get(p.id, 0),
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        }
        results.append(d)
    return results


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/", response_model=List[ProjectRead])
async def list_projects(
    orgSlug: str,
    stage: Optional[ProjectStage] = None,
    owner_id: Optional[uuid.UUID] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    auth: AuthenticatedUser = Depends(require_member),
    session: AsyncSession = Depends(get_session),
):
    """List projects for the org, optionally filtered by stage or owner."""
    stmt = select(Project).where(Project.org_id == auth.org_id)
    if stage:
        stmt = stmt.where(Project.stage == stage.value)
    if owner_id:
        stmt = stmt.where(Project.owner_id == owner_id)
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)

    result = await session.execute(stmt)
    projects = list(result.scalars().all())
    return await _enrich_task_counts(session, projects)


@router.post("/", response_model=ProjectRead, status_code=201)
async def create_project(
    orgSlug: str,
    project_in: ProjectCreate,
    auth: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Create a project (Admin only). Auto-creates a default project channel."""
    project = Project(
        name=project_in.name,
        type=project_in.type,
        description=project_in.description,
        stage=ProjectStage.DEFINITION.value,
        owner_id=project_in.owner_id or auth.user_id,
        links=project_in.links or {},
        org_id=auth.org_id,
    )
    session.add(project)
    await session.flush()  # get project.id

    # Auto-create default project channel
    channel = Channel(
        org_id=auth.org_id,
        project_id=project.id,
        name=f"{project.name}",
        type="project",
    )
    session.add(channel)

    # Auto-assign owner to project
    assignment = ProjectUserAssignment(
        project_id=project.id,
        user_id=project.owner_id,
        org_id=auth.org_id,
    )
    session.add(assignment)

    await session.commit()
    await session.refresh(project)

    # Emit SSE event
    await broadcast_event(
        session=session,
        org_id=auth.org_id,
        event_type="project.created",
        payload={
            "project_id": str(project.id),
            "name": project.name,
            "stage": project.stage,
            "owner_id": str(project.owner_id),
            "type": project.type,
        },
        actor_id=auth.user_id,
        actor_type="human",
    )

    enriched = await _enrich_task_counts(session, [project])
    return enriched[0]


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    orgSlug: str,
    project_id: uuid.UUID,
    auth: AuthenticatedUser = Depends(require_member),
    session: AsyncSession = Depends(get_session),
):
    project = await _get_project_or_404(session, project_id, auth.org_id)
    enriched = await _enrich_task_counts(session, [project])
    return enriched[0]


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    orgSlug: str,
    project_id: uuid.UUID,
    project_in: ProjectUpdate,
    auth: AuthenticatedUser = Depends(require_contributor),
    session: AsyncSession = Depends(get_session),
):
    project = await _get_project_or_404(session, project_id, auth.org_id)
    update_data = project_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(project, key, value)

    session.add(project)
    await session.commit()
    await session.refresh(project)

    await broadcast_event(
        session=session,
        org_id=auth.org_id,
        event_type="project.updated",
        payload={
            "project_id": str(project.id),
            **update_data,
        },
        actor_id=auth.user_id,
        actor_type="human",
    )

    enriched = await _enrich_task_counts(session, [project])
    return enriched[0]


@router.post("/{project_id}/transition", response_model=ProjectRead)
async def transition_project(
    orgSlug: str,
    project_id: uuid.UUID,
    body: ProjectTransition,
    auth: AuthenticatedUser = Depends(require_contributor),
    session: AsyncSession = Depends(get_session),
):
    """Transition a project to a new lifecycle stage."""
    project = await _get_project_or_404(session, project_id, auth.org_id)

    current_stage = ProjectStage(project.stage)
    is_valid, error_msg = validate_transition(current_stage, body.to_stage)
    if not is_valid:
        raise HTTPException(status_code=422, detail=error_msg)

    old_stage = project.stage
    project.stage = body.to_stage.value
    session.add(project)
    await session.commit()
    await session.refresh(project)

    await broadcast_event(
        session=session,
        org_id=auth.org_id,
        event_type="project.transitioned",
        payload={
            "project_id": str(project.id),
            "from_stage": old_stage,
            "to_stage": body.to_stage.value,
            "name": project.name,
        },
        actor_id=auth.user_id,
        actor_type="human",
    )

    enriched = await _enrich_task_counts(session, [project])
    return enriched[0]


@router.delete("/{project_id}")
async def delete_project(
    orgSlug: str,
    project_id: uuid.UUID,
    auth: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """End-of-life (delete) a project. Admin only."""
    project = await _get_project_or_404(session, project_id, auth.org_id)

    await broadcast_event(
        session=session,
        org_id=auth.org_id,
        event_type="project.deleted",
        payload={
            "project_id": str(project.id),
            "name": project.name,
        },
        actor_id=auth.user_id,
        actor_type="human",
    )

    await session.delete(project)
    await session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Project Membership
# ---------------------------------------------------------------------------


@router.post("/{project_id}/members", status_code=201)
async def add_project_members(
    orgSlug: str,
    project_id: uuid.UUID,
    body: ProjectMemberAdd,
    auth: AuthenticatedUser = Depends(require_contributor),
    session: AsyncSession = Depends(get_session),
):
    """Assign users to a project (grants channel access)."""
    project = await _get_project_or_404(session, project_id, auth.org_id)

    added = []
    for uid in body.user_ids:
        # Check if already assigned
        existing = await session.execute(
            select(ProjectUserAssignment).where(
                ProjectUserAssignment.project_id == project.id,
                ProjectUserAssignment.user_id == uid,
            )
        )
        if existing.scalar_one_or_none():
            continue
        assignment = ProjectUserAssignment(
            project_id=project.id,
            user_id=uid,
            org_id=auth.org_id,
        )
        session.add(assignment)
        added.append(str(uid))

    await session.commit()
    return {"added": added}


@router.delete("/{project_id}/members/{user_id}")
async def remove_project_member(
    orgSlug: str,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    auth: AuthenticatedUser = Depends(require_contributor),
    session: AsyncSession = Depends(get_session),
):
    """Remove a user from a project."""
    project = await _get_project_or_404(session, project_id, auth.org_id)
    result = await session.execute(
        select(ProjectUserAssignment).where(
            ProjectUserAssignment.project_id == project.id,
            ProjectUserAssignment.user_id == user_id,
        )
    )
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="User not assigned to project")
    await session.delete(assignment)
    await session.commit()
    return {"ok": True}
