"""Request/response models for numbering endpoints."""

import uuid
from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.modules.numbering.pattern import InvalidPatternError, Pattern, ResetPeriod

DocumentType = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z_]{1,39}$")]


def _valid_pattern(value: str) -> str:
    try:
        Pattern.parse(value)
    except InvalidPatternError as exc:
        raise ValueError(str(exc)) from None
    return value


class SchemeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_type: str
    branch_id: uuid.UUID | None
    pattern: str
    reset_period: ResetPeriod
    start_at: int
    is_active: bool
    version: int


class SchemeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: DocumentType
    branch_id: uuid.UUID | None = None
    pattern: str = Field(examples=["INV-{BRANCH}-{YYYY}-{SEQ:5}"])
    reset_period: ResetPeriod = ResetPeriod.YEARLY
    start_at: Annotated[int, Field(ge=1, le=10**12)] = 1

    _pattern = field_validator("pattern")(_valid_pattern)


class SchemeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pattern: str | None = None
    reset_period: ResetPeriod | None = None
    is_active: bool | None = None

    @field_validator("pattern")
    @classmethod
    def _pattern(cls, value: str | None) -> str | None:
        return None if value is None else _valid_pattern(value)


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pattern: str
    on: date | None = None
    branch_code: Annotated[str, StringConstraints(pattern=r"^[A-Z0-9]{1,10}$")] | None = None

    _pattern = field_validator("pattern")(_valid_pattern)


class PreviewOut(BaseModel):
    examples: list[str] = Field(description="The first three numbers the pattern would produce")
