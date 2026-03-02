"""Sub-agent Pydantic schemas for shared use across server and frontend codegen."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, Field, ConfigDict
from pydantic import UUID4


class SubAgentBase(BaseModel):
    task_id: UUID4
    model: str
    instructions: str
    timeout_minutes: int = Field(default=60, ge=1, le=1440)


class SubAgentCreate(SubAgentBase):
    pass


class SubAgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID4
    org_id: UUID4
    task_id: UUID4
    model: str
    instructions: str
    status: str
    created_by: UUID4
    created_at: datetime
    expires_at: datetime
    terminated_at: Optional[datetime] = None
    termination_reason: Optional[str] = None


class SubAgentSpawnResponse(BaseModel):
    sub_agent: SubAgentRead
    api_key: str  # Plaintext key returned only once


class SubAgentTerminateRequest(BaseModel):
    reason: Optional[str] = None
