"""Request/response models for clients. The ID number is write-only: responses show a masked hint."""

import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.core.phone import InvalidPhoneError, to_e164

Kind = Literal["individual", "corporate"]
Channel = Literal["whatsapp", "sms", "email", "call"]
IdType = Literal["national_id", "passport", "alien_id", "business_registration"]
Source = Literal["walk_in", "referral", "lead", "social", "website", "other"]
HouseholdRole = Literal["head", "spouse", "child", "parent", "other"]
ActivityKind = Literal["note", "call", "meeting", "whatsapp", "sms", "email", "visit"]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
KraPin = Annotated[
    str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[APap]\d{9}[A-Za-z]$")
]
Tag = Annotated[
    str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=1, max_length=30)
]


def _phone(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    try:
        return to_e164(value)
    except InvalidPhoneError as exc:
        raise ValueError(str(exc)) from None


class Address(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line1: Text | None = None
    town: Text | None = None
    county: Text | None = None
    postal_code: Annotated[str, StringConstraints(max_length=20)] | None = None


class _ClientFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: Name | None = None
    last_name: Name | None = None
    other_names: Name | None = None
    company_name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
        | None
    ) = None
    email: EmailStr | None = None
    phone: str | None = Field(default=None, examples=["0712 345 678"])
    alt_phone: str | None = None
    preferred_channel: Channel | None = None
    kra_pin: KraPin | None = None
    id_type: IdType | None = None
    id_number: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=30)] | None
    ) = Field(
        default=None, description="Write-only. Stored encrypted; responses show `id_number_hint`."
    )
    date_of_birth: date | None = None
    gender: Literal["female", "male", "other"] | None = None
    occupation: Text | None = None
    address: Address | None = None
    source: Source | None = None
    referred_by_id: uuid.UUID | None = None
    tags: list[Tag] | None = Field(default=None, max_length=20)
    owner_user_id: Annotated[str, StringConstraints(min_length=1, max_length=255)] | None = None
    household_id: uuid.UUID | None = None
    household_role: HouseholdRole | None = None
    marketing_consent: bool | None = None
    notes: Annotated[str, StringConstraints(max_length=5000)] | None = None

    _phones = field_validator("phone", "alt_phone")(lambda cls, v: _phone(v))

    @field_validator("date_of_birth")
    @classmethod
    def _dob(cls, value: date | None) -> date | None:
        if value is not None and not date(1900, 1, 1) <= value <= datetime.now(UTC).date():
            raise ValueError("Date of birth must be in the past")
        return value


class ClientCreate(_ClientFields):
    kind: Kind = "individual"
    allow_duplicate: bool = Field(
        default=False,
        description="Create even if a client with the same phone, email, PIN or ID exists",
    )

    @model_validator(mode="after")
    def _names(self) -> Self:
        if self.kind == "individual" and not (self.first_name and self.last_name):
            raise ValueError("Individual clients need a first and last name")
        if self.kind == "corporate" and not self.company_name:
            raise ValueError("Corporate clients need a company name")
        if self.id_number and not self.id_type:
            self.id_type = "national_id" if self.kind == "individual" else "business_registration"
        return self


class ClientUpdate(_ClientFields):
    archived: bool | None = None


class ClientSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    display_name: str
    email: str | None
    phone: str | None
    kra_pin: str | None
    tags: list[str]
    owner_user_id: str | None
    household_id: uuid.UUID | None
    status: str
    created_at: datetime


class ClientOut(ClientSummary):
    first_name: str | None
    last_name: str | None
    other_names: str | None
    company_name: str | None
    alt_phone: str | None
    preferred_channel: str
    id_type: str | None
    id_number_hint: str | None
    date_of_birth: date | None
    gender: str | None
    occupation: str | None
    address: dict[str, Any]
    source: str | None
    referred_by_id: uuid.UUID | None
    household_role: str | None
    marketing_consent: bool
    marketing_consent_at: datetime | None
    notes: str | None
    archived_at: datetime | None
    updated_at: datetime
    version: int


class DuplicateCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr | None = None
    phone: str | None = None
    kra_pin: str | None = None
    id_number: str | None = None
    exclude_id: uuid.UUID | None = None

    _phone = field_validator("phone")(lambda cls, v: _phone(v))


class DuplicateMatch(BaseModel):
    client: ClientSummary
    matched_on: list[Literal["phone", "email", "kra_pin", "id_number"]]


class DuplicateResult(BaseModel):
    matches: list[DuplicateMatch]
    hidden: int = Field(description="Matches among clients you cannot see (another agent's book)")


class ContactIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    role: Text | None = None
    email: EmailStr | None = None
    phone: str | None = None
    is_primary: bool = False

    _phone = field_validator("phone")(lambda cls, v: _phone(v))


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    role: str | None
    email: str | None
    phone: str | None
    is_primary: bool


class ActivityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ActivityKind = "note"
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]
    occurred_at: datetime | None = None


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    body: str
    occurred_at: datetime
    created_by: str | None


class HouseholdIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    notes: Annotated[str, StringConstraints(max_length=2000)] | None = None


class HouseholdOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    notes: str | None
    version: int


class HouseholdDetail(HouseholdOut):
    members: list[ClientSummary]


class TimelineItem(BaseModel):
    """One entry in the client's 360° timeline, newest first."""

    at: datetime
    kind: str = Field(description="activity | document | task | message | change")
    title: str
    detail: str | None = None
    actor: str | None = None
    ref: dict[str, str] = Field(
        default_factory=dict, description="ids to open the item, e.g. document_id"
    )
