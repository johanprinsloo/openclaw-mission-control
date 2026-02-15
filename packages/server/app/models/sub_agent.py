"""Sub-agent model (RLS-scoped)."""

from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlmodel import Field, SQLModel

from .base import UUIDMixin


class SubAgent(SQLModel, table=True):
    __tablename__ = "sub_agents"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    org_id: uuid.UUID = Field(foreign_key="organizations.id", nullable=False, index=True)
    task_id: uuid.UUID = Field(foreign_key="tasks.id", nullable=False)
    model: str = Field(nullable=False)
    instructions: str = Field(nullable=False)
    status: str = Field(default="active", nullable=False)  # active | terminated
    created_by: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    api_key_hash: Optional[str] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
        sa_column_kwargs={"server_default": "now()"},
    )
    expires_at: datetime = Field(nullable=False)
    terminated_at: Optional[datetime] = None
    termination_reason: Optional[str] = None
