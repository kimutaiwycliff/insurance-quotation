"""Request/response models for public links."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

Scope = Literal["view", "accept", "pay"]


class SendTo(BaseModel):
    """Email the link to the client right away (logged in the outbound messages)."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    message: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] = ""


class LinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z_]{1,39}$")]
    entity_id: uuid.UUID
    scopes: list[Scope] = Field(default_factory=lambda: list[Scope](["view"]), min_length=1)
    expires_in_days: Annotated[int, Field(ge=1, le=365)] | None = None
    send_to: SendTo | None = None


class LinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    scopes: list[str]
    expires_at: datetime
    revoked_at: datetime | None
    created_at: datetime
    view_count: int
    last_viewed_at: datetime | None


class LinkCreated(LinkOut):
    message_id: uuid.UUID | None = Field(
        default=None, description="Outbound email, if `send_to` was given"
    )
    url: str = Field(
        description="Share this. The token is shown only once and stored only as a hash."
    )
    token: str


class LinkEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    occurred_at: datetime
    is_bot: bool
    details: dict[str, object]


class PublicTenant(BaseModel):
    name: str


class Choice(BaseModel):
    position: int
    label: str
    amount: str
    currency: str
    recommended: bool = False


class PublicLinkView(BaseModel):
    """What an anonymous visitor may learn about a link. No internal ids."""

    tenant: PublicTenant
    title: str
    kind: str
    scopes: list[str]
    expires_at: datetime
    has_web_view: bool
    has_download: bool
    state: str | None = None
    choices: list[Choice] = Field(default_factory=list)


class ActionResult(BaseModel):
    state: str


class Beacon(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duration_ms: Annotated[int, Field(ge=0, le=24 * 3600 * 1000)] | None = None
