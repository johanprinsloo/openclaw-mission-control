from typing import Optional
from sqlmodel import SQLModel, Field, Relationship
import uuid
import enum

from app.models.base import TimestampMixin, UUIDMixin

class ChannelType(str, enum.Enum):
    ORG_WIDE = "org_wide"
    PROJECT = "project"

class Channel(UUIDMixin, TimestampMixin, SQLModel, table=True):
    __tablename__ = "channels"

    org_id: uuid.UUID = Field(foreign_key="organizations.id", index=True, nullable=False)
    project_id: Optional[uuid.UUID] = Field(foreign_key="projects.id", index=True, nullable=True)
    name: str = Field(nullable=False)
    type: ChannelType = Field(nullable=False)

    # Relationships are handled separately if needed for backref, 
    # but for now we'll just define the forward relationship if needed for queries.
    # organization: "Organization" = Relationship(back_populates="channels")
    # project: Optional["Project"] = Relationship(back_populates="channels")
