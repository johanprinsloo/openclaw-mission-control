from typing import Optional, List
from datetime import datetime
from sqlmodel import Field, Relationship, SQLModel
from sqlalchemy.dialects.postgresql import JSONB
from .base import TimestampMixin, UUIDMixin

class Organization(UUIDMixin, TimestampMixin, table=True):
    __tablename__ = "organizations"

    name: str = Field(index=True)
    slug: str = Field(unique=True, index=True)
    status: str = Field(default="active")
    settings: dict = Field(default_factory=dict, sa_type=JSONB)
    deletion_scheduled_at: Optional[datetime] = None
    
    # Relationships
    # users: List["UserOrg"] = Relationship(back_populates="organization")
    # projects: List["Project"] = Relationship(back_populates="organization")
    # tasks: List["Task"] = Relationship(back_populates="organization")
