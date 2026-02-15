from typing import Optional, List
from datetime import datetime
from sqlmodel import Field, Relationship, SQLModel
from sqlalchemy.dialects.postgresql import JSONB
import uuid
from .base import TimestampMixin, UUIDMixin

class Project(UUIDMixin, TimestampMixin, table=True):
    __tablename__ = "projects"

    name: str
    description: Optional[str] = None
    stage: str = Field(default="definition")
    owner_id: Optional[uuid.UUID] = Field(foreign_key="users.id")
    links: dict = Field(default_factory=dict, sa_type=JSONB)
    org_id: uuid.UUID = Field(foreign_key="organizations.id", index=True)

    # tasks: List["TaskProjectAssignment"] = Relationship(back_populates="project")
    # members: List["ProjectUserAssignment"] = Relationship(back_populates="project")
