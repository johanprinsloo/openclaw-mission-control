from typing import Optional, List
from datetime import datetime
from sqlmodel import Field, Relationship, SQLModel
from .base import TimestampMixin, UUIDMixin

class User(UUIDMixin, TimestampMixin, table=True):
    __tablename__ = "users"
    
    email: Optional[str] = Field(unique=True, index=True)
    type: str  # human | agent
    identifier: Optional[str] = None
    oidc_provider: Optional[str] = None
    oidc_subject: Optional[str] = None
    
    # Relationships
    # orgs: List["UserOrg"] = Relationship(back_populates="user")
    # projects: List["ProjectUserAssignment"] = Relationship(back_populates="user")
