"""Task-related Pydantic schemas for shared use across server and frontend codegen."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field
from pydantic import UUID4

from .common import EvidenceType, TaskPriority, TaskStatus


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

class EvidenceSubmission(BaseModel):
    """A single piece of evidence submitted during a task transition."""
    type: EvidenceType
    url: str


class EvidenceRead(BaseModel):
    id: UUID4
    task_id: UUID4
    type: EvidenceType
    url: str
    submitted_at: datetime
    submitted_by: UUID4


# ---------------------------------------------------------------------------
# Task CRUD
# ---------------------------------------------------------------------------

class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    type: str = "chore"  # bug | feature | chore
    priority: TaskPriority = TaskPriority.MEDIUM
    required_evidence_types: List[EvidenceType] = Field(default_factory=list)


class TaskCreate(TaskBase):
    project_ids: List[UUID4] = Field(default_factory=list)
    assignee_ids: List[UUID4] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    priority: Optional[TaskPriority] = None
    required_evidence_types: Optional[List[EvidenceType]] = None
    project_ids: Optional[List[UUID4]] = None
    assignee_ids: Optional[List[UUID4]] = None


class TaskRead(BaseModel):
    id: UUID4
    org_id: UUID4
    title: str
    description: Optional[str] = None
    type: str
    priority: str
    status: str
    required_evidence_types: List[str] = Field(default_factory=list)
    project_ids: List[UUID4] = Field(default_factory=list)
    assignee_ids: List[UUID4] = Field(default_factory=list)
    dependency_ids: List[UUID4] = Field(default_factory=list)
    evidence: List[EvidenceRead] = Field(default_factory=list)
    completed_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Transition
# ---------------------------------------------------------------------------

class TaskTransition(BaseModel):
    """Request body for POST /tasks/{taskId}/transition."""
    to_status: TaskStatus
    evidence: List[EvidenceSubmission] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

class DependencyAdd(BaseModel):
    """Request body for POST /tasks/{taskId}/dependencies."""
    blocked_by_id: UUID4


class DependencyRead(BaseModel):
    task_id: UUID4
    blocked_by_id: UUID4
