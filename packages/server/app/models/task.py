"""Task model."""

from datetime import datetime
from typing import List, Optional
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, VARCHAR
from sqlmodel import Field, SQLModel

from .base import TimestampMixin, UUIDMixin


class Task(UUIDMixin, TimestampMixin, SQLModel, table=True):
    __tablename__ = "tasks"

    org_id: uuid.UUID = Field(foreign_key="organizations.id", nullable=False, index=True)
    title: str = Field(nullable=False)
    description: Optional[str] = None
    type: str = Field(nullable=False, default="chore")  # bug | feature | chore
    priority: str = Field(nullable=False, default="medium")  # low | medium | high | critical
    status: str = Field(nullable=False, default="backlog")  # backlog | in-progress | in-review | complete
    required_evidence_types: List[str] = Field(default_factory=list, sa_type=ARRAY(VARCHAR))
    completed_at: Optional[datetime] = Field(default=None, sa_type=sa.DateTime(timezone=True))
    archived_at: Optional[datetime] = Field(default=None, sa_type=sa.DateTime(timezone=True))
