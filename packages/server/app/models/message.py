from typing import Optional, List
from datetime import datetime
from sqlmodel import SQLModel, Field
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID, ARRAY
import uuid

class Message(SQLModel, table=True):
    __tablename__ = "messages"
    __table_args__ = (
        {"postgresql_partition_by": "RANGE (created_at)"},
    )

    id: uuid.UUID = Field(primary_key=True, default_factory=uuid.uuid4)
    org_id: uuid.UUID = Field(foreign_key="organizations.id", index=True, nullable=False)
    channel_id: uuid.UUID = Field(foreign_key="channels.id", index=True, nullable=False)
    sender_id: uuid.UUID = Field(foreign_key="users.id", index=True, nullable=False)
    content: str = Field(nullable=False)
    mentions: List[uuid.UUID] = Field(default=[], sa_column=Column(ARRAY(UUID(as_uuid=True)), server_default="{}"))
    created_at: datetime = Field(primary_key=True, default_factory=datetime.utcnow, index=True)
