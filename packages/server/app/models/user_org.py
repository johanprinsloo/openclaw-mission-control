"""User-Organization membership (join table, RLS-scoped)."""

from typing import Optional
import uuid

from sqlmodel import Field, SQLModel


class UserOrg(SQLModel, table=True):
    __tablename__ = "users_orgs"

    user_id: uuid.UUID = Field(foreign_key="users.id", primary_key=True)
    org_id: uuid.UUID = Field(foreign_key="organizations.id", primary_key=True)
    role: str = Field(nullable=False, default="contributor")  # administrator | contributor
    display_name: str = Field(nullable=False)
    api_key_hash: Optional[str] = None
