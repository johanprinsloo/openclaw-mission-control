"""User model."""

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel

from .base import UUIDMixin


class User(UUIDMixin, SQLModel, table=True):
    __tablename__ = "users"

    email: Optional[str] = Field(default=None, unique=True, index=True)
    type: str = Field(nullable=False)  # human | agent
    identifier: Optional[str] = None
    oidc_provider: Optional[str] = None
    oidc_subject: Optional[str] = None
    created_at: datetime = Field(
        default_factory=lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        nullable=False,
        sa_column_kwargs={"server_default": "now()"},
    )
