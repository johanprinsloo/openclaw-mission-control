"""
Task service layer: business logic for tasks, dependencies, and evidence.

Handles:
- Task CRUD with project/assignee assignments
- Status transitions with evidence validation gate
- Dependency management with circular dependency detection
- Enrichment of task data for API responses
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import List, Optional, Sequence

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.assignments import TaskProjectAssignment, TaskUserAssignment
from app.models.dependency import TaskDependency
from app.models.task import Task
from app.models.task_evidence import TaskEvidence
from openclaw_mc_shared.schemas.common import TaskStatus
from openclaw_mc_shared.schemas.tasks import (
    EvidenceRead,
    EvidenceSubmission,
    TaskCreate,
    TaskRead,
    TaskUpdate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def get_task_or_404(
    session: AsyncSession, task_id: uuid.UUID, org_id: uuid.UUID
) -> Task:
    task = await session.get(Task, task_id)
    if not task or task.org_id != org_id:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


async def _get_project_ids(session: AsyncSession, task_id: uuid.UUID) -> list[uuid.UUID]:
    result = await session.execute(
        select(TaskProjectAssignment.project_id).where(
            TaskProjectAssignment.task_id == task_id
        )
    )
    return [row[0] for row in result.all()]


async def _get_assignee_ids(session: AsyncSession, task_id: uuid.UUID) -> list[uuid.UUID]:
    result = await session.execute(
        select(TaskUserAssignment.user_id).where(
            TaskUserAssignment.task_id == task_id
        )
    )
    return [row[0] for row in result.all()]


async def _get_dependency_ids(session: AsyncSession, task_id: uuid.UUID) -> list[uuid.UUID]:
    result = await session.execute(
        select(TaskDependency.blocked_by_id).where(
            TaskDependency.task_id == task_id
        )
    )
    return [row[0] for row in result.all()]


async def _get_evidence(session: AsyncSession, task_id: uuid.UUID) -> list[EvidenceRead]:
    result = await session.execute(
        select(TaskEvidence).where(TaskEvidence.task_id == task_id)
    )
    rows = result.scalars().all()
    return [
        EvidenceRead(
            id=e.id,
            task_id=e.task_id,
            type=e.type,
            url=e.url,
            submitted_at=e.submitted_at,
            submitted_by=e.submitted_by,
        )
        for e in rows
    ]


async def enrich_task(session: AsyncSession, task: Task) -> TaskRead:
    """Convert a Task ORM object to a TaskRead with all related data."""
    project_ids = await _get_project_ids(session, task.id)
    assignee_ids = await _get_assignee_ids(session, task.id)
    dependency_ids = await _get_dependency_ids(session, task.id)
    evidence = await _get_evidence(session, task.id)

    return TaskRead(
        id=task.id,
        org_id=task.org_id,
        title=task.title,
        description=task.description,
        type=task.type,
        priority=task.priority,
        status=task.status,
        required_evidence_types=task.required_evidence_types or [],
        project_ids=project_ids,
        assignee_ids=assignee_ids,
        dependency_ids=dependency_ids,
        evidence=evidence,
        completed_at=task.completed_at,
        archived_at=task.archived_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


async def enrich_tasks(session: AsyncSession, tasks: Sequence[Task]) -> list[TaskRead]:
    """Enrich a list of tasks. TODO: batch queries for performance."""
    return [await enrich_task(session, t) for t in tasks]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create_task(
    session: AsyncSession,
    task_in: TaskCreate,
    org_id: uuid.UUID,
) -> Task:
    task = Task(
        org_id=org_id,
        title=task_in.title,
        description=task_in.description,
        type=task_in.type,
        priority=task_in.priority.value,
        status=TaskStatus.BACKLOG.value,
        required_evidence_types=[e.value for e in task_in.required_evidence_types],
    )
    session.add(task)
    await session.flush()

    # Assign projects
    for pid in task_in.project_ids:
        session.add(TaskProjectAssignment(task_id=task.id, project_id=pid, org_id=org_id))

    # Assign users
    for uid in task_in.assignee_ids:
        session.add(TaskUserAssignment(task_id=task.id, user_id=uid, org_id=org_id))

    await session.flush()
    return task


async def update_task(
    session: AsyncSession,
    task: Task,
    task_in: TaskUpdate,
    org_id: uuid.UUID,
) -> Task:
    data = task_in.model_dump(exclude_unset=True)

    # Handle project assignments
    if "project_ids" in data:
        project_ids = data.pop("project_ids")
        # Remove existing
        existing = await session.execute(
            select(TaskProjectAssignment).where(TaskProjectAssignment.task_id == task.id)
        )
        for a in existing.scalars().all():
            await session.delete(a)
        # Add new
        for pid in project_ids:
            session.add(TaskProjectAssignment(task_id=task.id, project_id=pid, org_id=org_id))

    # Handle assignee assignments
    if "assignee_ids" in data:
        assignee_ids = data.pop("assignee_ids")
        existing = await session.execute(
            select(TaskUserAssignment).where(TaskUserAssignment.task_id == task.id)
        )
        for a in existing.scalars().all():
            await session.delete(a)
        for uid in assignee_ids:
            session.add(TaskUserAssignment(task_id=task.id, user_id=uid, org_id=org_id))

    # Handle evidence types (convert enums to strings)
    if "required_evidence_types" in data and data["required_evidence_types"] is not None:
        data["required_evidence_types"] = [e.value if hasattr(e, "value") else e for e in data["required_evidence_types"]]

    for key, value in data.items():
        if hasattr(task, key):
            setattr(task, key, value)

    session.add(task)
    await session.flush()
    return task


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------

VALID_TRANSITIONS = {
    TaskStatus.BACKLOG: [TaskStatus.IN_PROGRESS],
    TaskStatus.IN_PROGRESS: [TaskStatus.BACKLOG, TaskStatus.IN_REVIEW],
    TaskStatus.IN_REVIEW: [TaskStatus.IN_PROGRESS, TaskStatus.COMPLETE],
    TaskStatus.COMPLETE: [TaskStatus.IN_REVIEW],  # reopen
}


async def transition_task(
    session: AsyncSession,
    task: Task,
    to_status: TaskStatus,
    evidence: list[EvidenceSubmission],
    actor_id: uuid.UUID,
    org_id: uuid.UUID,
) -> Task:
    current = TaskStatus(task.status)

    # Validate transition
    allowed = VALID_TRANSITIONS.get(current, [])
    if to_status not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot transition from '{current.value}' to '{to_status.value}'. "
            f"Allowed: {[s.value for s in allowed]}",
        )

    # If completing, check dependencies are all complete
    if to_status == TaskStatus.COMPLETE:
        dep_ids = await _get_dependency_ids(session, task.id)
        if dep_ids:
            result = await session.execute(
                select(Task).where(Task.id.in_(dep_ids))
            )
            blockers = [t for t in result.scalars().all() if t.status != TaskStatus.COMPLETE.value]
            if blockers:
                names = ", ".join(b.title for b in blockers)
                raise HTTPException(
                    status_code=422,
                    detail=f"Cannot complete: blocking dependencies not complete: {names}",
                )

    # Evidence gate
    if to_status == TaskStatus.COMPLETE and task.required_evidence_types:
        required = set(task.required_evidence_types)
        # Include already-submitted evidence
        existing_evidence = await _get_evidence(session, task.id)
        submitted = set(e.type.value if hasattr(e.type, "value") else e.type for e in existing_evidence)
        # Add newly submitted evidence types
        for ev in evidence:
            submitted.add(ev.type.value)
        missing = required - submitted
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"Missing required evidence types: {sorted(missing)}",
            )

    # Save new evidence
    for ev in evidence:
        te = TaskEvidence(
            task_id=task.id,
            org_id=org_id,
            type=ev.type.value,
            url=ev.url,
            submitted_by=actor_id,
        )
        session.add(te)

    old_status = task.status
    task.status = to_status.value
    if to_status == TaskStatus.COMPLETE:
        task.completed_at = datetime.utcnow()
    elif old_status == TaskStatus.COMPLETE.value:
        task.completed_at = None  # reopen

    session.add(task)
    await session.flush()
    return task


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


async def _has_path(
    session: AsyncSession,
    from_id: uuid.UUID,
    to_id: uuid.UUID,
    org_id: uuid.UUID,
) -> bool:
    """BFS to detect if there's a path from from_id to to_id in the dependency graph."""
    # Build adjacency: task_id -> [blocked_by_id]
    result = await session.execute(
        select(TaskDependency).where(TaskDependency.org_id == org_id)
    )
    adj: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for dep in result.scalars().all():
        adj[dep.task_id].append(dep.blocked_by_id)

    # BFS from from_id following blocked_by edges
    visited: set[uuid.UUID] = set()
    queue = [from_id]
    while queue:
        current = queue.pop(0)
        if current == to_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        queue.extend(adj.get(current, []))
    return False


async def add_dependency(
    session: AsyncSession,
    task_id: uuid.UUID,
    blocked_by_id: uuid.UUID,
    org_id: uuid.UUID,
) -> None:
    if task_id == blocked_by_id:
        raise HTTPException(status_code=409, detail="A task cannot depend on itself")

    # Check both tasks exist in org
    task = await get_task_or_404(session, task_id, org_id)
    blocker = await get_task_or_404(session, blocked_by_id, org_id)

    # Check duplicate
    existing = await session.execute(
        select(TaskDependency).where(
            TaskDependency.task_id == task_id,
            TaskDependency.blocked_by_id == blocked_by_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Dependency already exists")

    # Check for circular dependency:
    # Adding task -> blocked_by means "task is blocked by blocked_by".
    # Circular if blocked_by is already (transitively) blocked by task.
    # i.e., there's already a path from blocked_by_id to task_id.
    if await _has_path(session, blocked_by_id, task_id, org_id):
        raise HTTPException(
            status_code=409,
            detail="Adding this dependency would create a circular dependency",
        )

    dep = TaskDependency(task_id=task_id, blocked_by_id=blocked_by_id, org_id=org_id)
    session.add(dep)
    await session.flush()


async def remove_dependency(
    session: AsyncSession,
    task_id: uuid.UUID,
    blocked_by_id: uuid.UUID,
    org_id: uuid.UUID,
) -> None:
    result = await session.execute(
        select(TaskDependency).where(
            TaskDependency.task_id == task_id,
            TaskDependency.blocked_by_id == blocked_by_id,
        )
    )
    dep = result.scalar_one_or_none()
    if not dep:
        raise HTTPException(status_code=404, detail="Dependency not found")
    await session.delete(dep)
    await session.flush()
