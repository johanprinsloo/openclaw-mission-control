from typing import Optional, Dict, List
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from .common import ProjectStage, PROJECT_STAGE_ORDER


class ProjectBase(BaseModel):
    name: str
    type: str = "software"  # software | docs | launch
    description: Optional[str] = None
    links: Optional[Dict[str, str]] = Field(default_factory=dict)
    owner_id: Optional[UUID] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    links: Optional[Dict[str, str]] = None
    owner_id: Optional[UUID] = None


class ProjectTransition(BaseModel):
    to_stage: ProjectStage


class ProjectRead(ProjectBase):
    id: UUID
    org_id: UUID
    stage: ProjectStage
    task_count: int = 0
    task_complete_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectMemberAdd(BaseModel):
    user_ids: List[UUID]


class ProjectMemberRead(BaseModel):
    user_id: UUID
    display_name: str
    type: str
    assigned_at: datetime


def validate_transition(current: ProjectStage, target: ProjectStage) -> tuple[bool, str]:
    """Validate a project lifecycle transition.

    Rules:
    - Forward transitions: only to the next adjacent stage.
    - Backward transitions: allowed to any earlier stage.

    Returns (is_valid, error_message).
    """
    if current == target:
        return False, f"Project is already in {current.value} stage"

    current_idx = PROJECT_STAGE_ORDER.index(current)
    target_idx = PROJECT_STAGE_ORDER.index(target)

    # Backward transition: always allowed
    if target_idx < current_idx:
        return True, ""

    # Forward transition: only one step at a time
    if target_idx == current_idx + 1:
        return True, ""

    return False, (
        f"Cannot transition from {current.value} to {target.value}. "
        f"Next forward stage is {PROJECT_STAGE_ORDER[current_idx + 1].value}"
    )
