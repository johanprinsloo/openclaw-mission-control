"""Sub-agent model (RLS-scoped)."""

from datetime import datetime, timezone
from typing import Optional
import uuid

import sqlalchemy as sa
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
        default_factory=lambda: datetime.utcnow(),
        nullable=False,
        sa_column_kwargs={"server_default": "now()"},
        sa_type=sa.DateTime(timezone=True),
    )
    expires_at: datetime = Field(nullable=False, sa_type=sa.DateTime(timezone=True))
    terminated_at: Optional[datetime] = Field(default=None, sa_type=sa.DateTime(timezone=True))
    termination_reason: Optional[str] = None
