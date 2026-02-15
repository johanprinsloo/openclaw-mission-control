"""Task dependency model (RLS-scoped)."""

import uuid

from sqlalchemy import CheckConstraint
from sqlmodel import Field, SQLModel


class TaskDependency(SQLModel, table=True):
    __tablename__ = "task_dependencies"
    __table_args__ = (
        CheckConstraint("task_id != blocked_by_id", name="no_self_dependency"),
    )

    task_id: uuid.UUID = Field(foreign_key="tasks.id", primary_key=True)
    blocked_by_id: uuid.UUID = Field(foreign_key="tasks.id", primary_key=True)
    org_id: uuid.UUID = Field(foreign_key="organizations.id", nullable=False, index=True)
