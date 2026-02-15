"""Subscription model (RLS-scoped)."""

import uuid

from sqlmodel import Field, SQLModel


class Subscription(SQLModel, table=True):
    __tablename__ = "subscriptions"

    user_id: uuid.UUID = Field(foreign_key="users.id", primary_key=True)
    org_id: uuid.UUID = Field(foreign_key="organizations.id", primary_key=True)
    topic_type: str = Field(primary_key=True, nullable=False)  # project | task | channel
    topic_id: uuid.UUID = Field(primary_key=True, nullable=False)
