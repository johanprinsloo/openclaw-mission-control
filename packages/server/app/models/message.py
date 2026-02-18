"""Message model (partitioned by month on created_at, RLS-scoped)."""

from datetime import datetime, timezone
from typing import List
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlmodel import Field, SQLModel


class Message(SQLModel, table=True):
    __tablename__ = "messages"
    __table_args__ = (
        {"postgresql_partition_by": "RANGE (created_at)"},
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    org_id: uuid.UUID = Field(foreign_key="organizations.id", nullable=False, index=True)
    channel_id: uuid.UUID = Field(foreign_key="channels.id", nullable=False, index=True)
    sender_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    content: str = Field(nullable=False)
    mentions: List[uuid.UUID] = Field(
        default_factory=list,
        sa_column=sa.Column(ARRAY(UUID(as_uuid=True)), server_default="{}"),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        primary_key=True,
        sa_column_kwargs={"server_default": "now()"},
        sa_type=sa.DateTime(timezone=True),
    )
