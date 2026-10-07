"""Request/response models for notifications."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    title: str
    body: str
    link: str | None
    read_at: datetime | None
    created_at: datetime


class UnreadCount(BaseModel):
    unread: int


class Preference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    in_app: bool
    email: bool
    description: str = Field(default="", description="Read-only")
