"""Request/response models for messaging."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    channel: str
    stream: str
    event: str
    to_address: str
    subject: str
    status: str
    attempts: int
    error: str | None
    entity_type: str | None
    entity_id: uuid.UUID | None
    created_at: datetime
    sent_at: datetime | None


class TemplateOut(BaseModel):
    event: str
    description: str
    stream: str
    locale: str
    subject: str
    body: str
    variables: list[str]
    customised: bool


class TemplateOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: Annotated[str, StringConstraints(min_length=1, max_length=300)]
    body: Annotated[str, StringConstraints(min_length=1, max_length=10_000)]
