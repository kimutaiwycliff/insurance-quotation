"""Request/response models for tasks."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

Priority = Literal["low", "normal", "high"]
Due = Literal["overdue", "today", "upcoming", "none", "all"]


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    notes: Annotated[str, StringConstraints(max_length=5000)] | None = None
    due_at: datetime | None = None
    assignee_user_id: Annotated[str, StringConstraints(min_length=1, max_length=255)] | None = None
    priority: Priority = "normal"
    entity_type: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z_]{1,39}$")] | None = None
    entity_id: uuid.UUID | None = None


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
        | None
    ) = None
    notes: Annotated[str, StringConstraints(max_length=5000)] | None = None
    due_at: datetime | None = None
    assignee_user_id: Annotated[str, StringConstraints(min_length=1, max_length=255)] | None = None
    priority: Priority | None = None
    done: bool | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    notes: str | None
    due_at: datetime | None
    assignee_user_id: str
    priority: str
    status: str
    completed_at: datetime | None
    entity_type: str | None
    entity_id: uuid.UUID | None
    created_by: str | None
    created_at: datetime
    version: int


class TaskCounts(BaseModel):
    overdue: int
    today: int
    upcoming: int
