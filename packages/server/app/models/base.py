"""Base mixins for SQLModel tables."""

from datetime import datetime, timezone
import sqlalchemy as sa
from sqlmodel import Field, SQLModel
import uuid


def _utcnow() -> datetime:
    return datetime.utcnow()


class TimestampMixin(SQLModel):
    created_at: datetime = Field(
        default_factory=_utcnow,
        nullable=False,
        sa_column_kwargs={"server_default": "now()"},
        sa_type=sa.DateTime(timezone=True),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        nullable=False,
        sa_column_kwargs={"server_default": "now()", "onupdate": _utcnow},
        sa_type=sa.DateTime(timezone=True),
    )


class UUIDMixin(SQLModel):
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        nullable=False,
    )
