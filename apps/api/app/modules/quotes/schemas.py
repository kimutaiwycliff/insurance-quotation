"""Request/response models for quotes."""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.core.money import AmountStr
from app.modules.insurers.service import RiskIn

Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Value = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class Detail(BaseModel):
    """A fact about the risk shown on the quote, e.g. Vehicle: KDA 123A, Toyota Axio 2019."""

    model_config = ConfigDict(extra="forbid")

    label: Label
    value: Value


class _Options(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_ids: list[uuid.UUID] = Field(min_length=1, max_length=8)
    risk: RiskIn
    recommended_product_id: uuid.UUID | None = None


class QuoteCreate(_Options):
    client_id: uuid.UUID
    title: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = None
    details: list[Detail] = Field(default_factory=list, max_length=12)
    notes: Annotated[str, StringConstraints(max_length=3000)] | None = None
    valid_days: Annotated[int, Field(ge=1, le=90)] = 30


class QuoteRecalculate(_Options):
    details: list[Detail] | None = Field(default=None, max_length=12)
    notes: Annotated[str, StringConstraints(max_length=3000)] | None = None


class OptionOut(BaseModel):
    position: int
    product_id: uuid.UUID
    insurer_name: str
    product_name: str
    excess_text: str | None
    client_total: AmountStr
    breakdown: dict[str, Any]
    commission: dict[str, Any] | None = Field(description="Only for roles that may see commission")
    needs_input: bool
    recommended: bool


class ClientRef(BaseModel):
    id: uuid.UUID
    display_name: str
    email: str | None
    phone: str | None


Status = Literal["draft", "sent", "accepted", "declined", "withdrawn", "expired"]


class QuoteSummary(BaseModel):
    id: uuid.UUID
    number: str | None
    title: str
    client: ClientRef
    class_code: str
    currency: str
    status: Status = Field(description="'expired' when a sent quote is past its validity")
    valid_until: date
    lowest_total: AmountStr | None
    options: int
    owner_user_id: str
    created_at: datetime


class QuoteOut(QuoteSummary):
    risk: dict[str, Any]
    details: list[Detail]
    notes: str | None
    sent_at: datetime | None
    accepted_position: int | None
    responded_at: datetime | None
    response: dict[str, Any]
    document_id: uuid.UUID | None
    option_list: list[OptionOut]
    version: int


class SendQuote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr | None = Field(
        default=None, description="defaults to the client's email; omit both to just get a link"
    )
    message: Annotated[str, StringConstraints(max_length=2000)] = ""


class Sent(BaseModel):
    quote: QuoteOut
    url: str = Field(description="Tracked link for the client (share on WhatsApp if not emailed)")
    emailed_to: str | None
    whatsapp_url: str | None


class AcceptBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option: Annotated[int, Field(ge=1, le=8)]
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)] | None = None
    email: EmailStr | None = None
    agree_terms: Literal[True] = Field(description="The client agrees to the quotation's terms")


class DeclineBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] = ""
