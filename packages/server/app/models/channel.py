"""Channel model (RLS-scoped)."""

from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlmodel import Field, SQLModel

from .base import UUIDMixin


class Channel(SQLModel, table=True):
    __tablename__ = "channels"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    org_id: uuid.UUID = Field(foreign_key="organizations.id", nullable=False, index=True)
    project_id: Optional[uuid.UUID] = Field(default=None, foreign_key="projects.id", index=True)
    name: str = Field(nullable=False)
    type: str = Field(nullable=False)  # org_wide | project
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
        sa_column_kwargs={"server_default": "now()"},
    )
