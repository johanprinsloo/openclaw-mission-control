"""Task evidence model (RLS-scoped)."""

from datetime import datetime, timezone
import uuid

from sqlmodel import Field, SQLModel

from .base import UUIDMixin


class TaskEvidence(SQLModel, table=True):
    __tablename__ = "task_evidence"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    task_id: uuid.UUID = Field(foreign_key="tasks.id", nullable=False, index=True)
    org_id: uuid.UUID = Field(foreign_key="organizations.id", nullable=False, index=True)
    type: str = Field(nullable=False)  # pr_link | test_results | doc_url
    url: str = Field(nullable=False)
    submitted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    submitted_by: uuid.UUID = Field(foreign_key="users.id", nullable=False)
