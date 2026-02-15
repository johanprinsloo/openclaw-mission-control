"""Organization model."""

from datetime import datetime
from typing import Optional

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from .base import TimestampMixin, UUIDMixin


class Organization(UUIDMixin, TimestampMixin, SQLModel, table=True):
    __tablename__ = "organizations"

    name: str = Field(nullable=False, index=True)
    slug: str = Field(unique=True, nullable=False, index=True)
    status: str = Field(default="active", nullable=False)
    settings: dict = Field(default_factory=dict, sa_type=JSONB, nullable=False)
    deletion_scheduled_at: Optional[datetime] = None
