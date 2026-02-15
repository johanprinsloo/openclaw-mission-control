from typing import Optional
from sqlmodel import Field, Relationship, SQLModel
from sqlalchemy.dialects.postgresql import UUID
import uuid

class UserOrg(SQLModel, table=True):
    __tablename__ = "users_orgs"

    user_id: uuid.UUID = Field(foreign_key="users.id", primary_key=True)
    org_id: uuid.UUID = Field(foreign_key="organizations.id", primary_key=True)
    role: str = Field(default="contributor")
    display_name: str
    api_key_hash: Optional[str] = None

    # user: "User" = Relationship(back_populates="orgs")
    # organization: "Organization" = Relationship(back_populates="users")
