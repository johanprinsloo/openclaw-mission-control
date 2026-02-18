"""User model."""

from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from .base import UUIDMixin


class User(UUIDMixin, SQLModel, table=True):
    __tablename__ = "users"

    email: Optional[str] = Field(default=None, unique=True, index=True)
    type: str = Field(nullable=False)  # human | agent
    identifier: Optional[str] = None
    oidc_provider: Optional[str] = None
    oidc_subject: Optional[str] = None
    password_hash: Optional[str] = Field(default=None)  # bcrypt hash for email/password login
    created_at: datetime = Field(
        default_factory=lambda: datetime.utcnow(),
        nullable=False,
        sa_column_kwargs={
            "server_default": sa.text("now()"),
        },
        sa_type=sa.DateTime(timezone=True),
    )
