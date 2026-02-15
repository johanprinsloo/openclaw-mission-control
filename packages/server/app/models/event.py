"""Event model (partitioned by month on timestamp, RLS-scoped, immutable)."""

from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class Event(SQLModel, table=True):
    __tablename__ = "events"
    __table_args__ = (
        {"postgresql_partition_by": "RANGE (timestamp)"},
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    sequence_id: Optional[int] = Field(default=None, index=True)  # auto-populated by DB sequence
    org_id: uuid.UUID = Field(foreign_key="organizations.id", nullable=False, index=True)
    type: str = Field(nullable=False)  # e.g., task.transitioned, project.created
    actor_id: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id")
    actor_type: str = Field(nullable=False)  # human | agent | system
    payload: dict = Field(default_factory=dict, sa_type=JSONB, nullable=False)
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        primary_key=True,
        sa_column_kwargs={"server_default": "now()"},
    )
