from typing import Optional, List
from pydantic import BaseModel, UUID4, Field
from datetime import datetime
from .common import TaskStatus, TaskPriority, EvidenceType

class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.BACKLOG
    required_evidence_types: Optional[List[EvidenceType]] = Field(default_factory=list)

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[TaskPriority] = None
    status: Optional[TaskStatus] = None
    required_evidence_types: Optional[List[EvidenceType]] = None

class TaskRead(TaskBase):
    id: UUID4
    org_id: UUID4
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None
