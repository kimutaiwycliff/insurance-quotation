"""Request/response models for leads."""

import uuid
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.core.money import MoneyModel
from app.core.phone import InvalidPhoneError, to_e164

Stage = Literal["new", "contacted", "quoted", "won", "lost"]
STAGES: tuple[Stage, ...] = ("new", "contacted", "quoted", "won", "lost")
LeadSource = Literal[
    "referral", "walk_in", "whatsapp", "facebook", "website", "event", "existing_client", "other"
]
Interest = Literal["motor", "medical", "life", "home", "business", "travel", "education", "other"]


def _phone(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    try:
        return to_e164(value)
    except InvalidPhoneError as exc:
        raise ValueError(str(exc)) from None


class _LeadFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str | None = None
    email: EmailStr | None = None
    source: LeadSource | None = None
    interests: list[Interest] | None = Field(default=None, max_length=8)
    estimated_premium: MoneyModel | None = Field(
        default=None, description="Rough annual premium, for the pipeline"
    )
    owner_user_id: Annotated[str, StringConstraints(min_length=1, max_length=255)] | None = None
    next_follow_up_at: datetime | None = None
    notes: Annotated[str, StringConstraints(max_length=5000)] | None = None

    _phone = field_validator("phone")(lambda cls, v: _phone(v))


class LeadCreate(_LeadFields):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]

    @model_validator(mode="after")
    def _reachable(self) -> Self:
        if not (self.phone or self.email):
            raise ValueError("Add a phone number or an email so you can follow up")
        return self


class LeadUpdate(_LeadFields):
    name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
        | None
    ) = None
    stage: Stage | None = None
    lost_reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = (
        None
    )


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    phone: str | None
    email: str | None
    source: str
    interests: list[str]
    stage: Stage
    lost_reason: str | None
    estimated_premium: MoneyModel | None
    owner_user_id: str
    next_follow_up_at: datetime | None
    notes: str | None
    client_id: uuid.UUID | None
    stage_changed_at: datetime | None
    created_at: datetime
    version: int


class ConvertLead(BaseModel):
    """Turn a won lead into a client: link an existing client, or create one from the lead's details."""

    model_config = ConfigDict(extra="forbid")

    client_id: uuid.UUID | None = None
    kind: Literal["individual", "corporate"] = "individual"
    first_name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
        | None
    ) = None
    last_name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
        | None
    ) = None
    company_name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
        | None
    ) = None
    allow_duplicate: bool = False


class StageSummary(BaseModel):
    stage: Stage
    count: int
    estimated_premium: MoneyModel


class Pipeline(BaseModel):
    stages: list[StageSummary]
    follow_ups_due: int = Field(description="Open leads whose follow-up time has passed")
