from typing import Optional
from datetime import datetime
from sqlmodel import Field, Relationship, SQLModel
import uuid

class TaskProjectAssignment(SQLModel, table=True):
    __tablename__ = "task_project_assignments"

    task_id: uuid.UUID = Field(foreign_key="tasks.id", primary_key=True)
    project_id: uuid.UUID = Field(foreign_key="projects.id", primary_key=True)
    org_id: uuid.UUID = Field(foreign_key="organizations.id", index=True)

    # task: "Task" = Relationship(back_populates="projects")
    # project: "Project" = Relationship(back_populates="tasks")


class ProjectUserAssignment(SQLModel, table=True):
    __tablename__ = "project_user_assignments"

    project_id: uuid.UUID = Field(foreign_key="projects.id", primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", primary_key=True)
    org_id: uuid.UUID = Field(foreign_key="organizations.id", index=True)
    assigned_at: datetime = Field(default_factory=datetime.utcnow)

    # project: "Project" = Relationship(back_populates="members")
    # user: "User" = Relationship(back_populates="projects")
