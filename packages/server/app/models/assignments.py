"""Assignment join tables (all RLS-scoped)."""

from datetime import datetime, timezone
import uuid

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class TaskProjectAssignment(SQLModel, table=True):
    __tablename__ = "task_project_assignments"

    task_id: uuid.UUID = Field(foreign_key="tasks.id", primary_key=True)
    project_id: uuid.UUID = Field(foreign_key="projects.id", primary_key=True)
    org_id: uuid.UUID = Field(foreign_key="organizations.id", nullable=False, index=True)


class ProjectUserAssignment(SQLModel, table=True):
    __tablename__ = "project_user_assignments"

    project_id: uuid.UUID = Field(foreign_key="projects.id", primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", primary_key=True)
    org_id: uuid.UUID = Field(foreign_key="organizations.id", nullable=False, index=True)
    assigned_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
        sa_type=sa.DateTime(timezone=True),
    )


class TaskUserAssignment(SQLModel, table=True):
    __tablename__ = "task_user_assignments"

    task_id: uuid.UUID = Field(foreign_key="tasks.id", primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", primary_key=True)
    org_id: uuid.UUID = Field(foreign_key="organizations.id", nullable=False, index=True)
