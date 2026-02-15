"""Project model."""

from typing import Optional
import uuid

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from .base import TimestampMixin, UUIDMixin


class Project(UUIDMixin, TimestampMixin, SQLModel, table=True):
    __tablename__ = "projects"

    org_id: uuid.UUID = Field(foreign_key="organizations.id", nullable=False, index=True)
    name: str = Field(nullable=False)
    type: str = Field(nullable=False)  # software | docs | launch
    description: Optional[str] = None
    stage: str = Field(default="definition", nullable=False)
    owner_id: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id")
    links: dict = Field(default_factory=dict, sa_type=JSONB, nullable=False)
