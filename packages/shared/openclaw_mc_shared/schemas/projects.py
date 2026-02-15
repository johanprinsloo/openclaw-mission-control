from typing import Optional, Dict
from pydantic import BaseModel, UUID4, Field
from datetime import datetime
from .common import ProjectStage

class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None
    stage: ProjectStage = ProjectStage.DEFINITION
    links: Optional[Dict[str, str]] = Field(default_factory=dict)
    owner_id: Optional[UUID4] = None

class ProjectCreate(ProjectBase):
    pass

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    stage: Optional[ProjectStage] = None
    links: Optional[Dict[str, str]] = None
    owner_id: Optional[UUID4] = None

class ProjectRead(ProjectBase):
    id: UUID4
    org_id: UUID4
    created_at: datetime
    updated_at: datetime
