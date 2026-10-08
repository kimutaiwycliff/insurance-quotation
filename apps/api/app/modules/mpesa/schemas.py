"""Request/response models for M-Pesa collection."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.core.money import AmountStr

Shortcode = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\d{5,7}$")]
Secret = Annotated[str, StringConstraints(strip_whitespace=True, min_length=8, max_length=200)]


class ConnectionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment: Literal["sandbox", "production", "simulator"] = Field(
        description="simulator: no network, every prompt is paid (not available in production)"
    )
    shortcode_type: Literal["paybill", "till"]
    business_shortcode: Shortcode = Field(
        description="Paybill number, or the store number of a Till"
    )
    till_number: Shortcode | None = Field(default=None, description="Till only: the till number")
    consumer_key: Secret
    consumer_secret: Secret
    passkey: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=200)]


class ConnectionOut(BaseModel):
    environment: str
    shortcode_type: str
    business_shortcode: str
    party_b: str
    status: str
    consumer_key_hint: str
    c2b_registered_at: datetime | None
    last_error: str | None
    stk_callback_url: str
    c2b_confirmation_url: str
    c2b_validation_url: str
    version: int


class PromptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=9, max_length=20)] | None
    ) = Field(default=None, description="Defaults to the client's phone")


class PromptOut(BaseModel):
    id: uuid.UUID
    invoice_id: uuid.UUID | None
    phone: str
    amount: AmountStr
    status: str = Field(description="pending, paid, cancelled, failed or expired")
    result_desc: str | None
    receipt: str | None
    payment_id: uuid.UUID | None
    created_at: datetime
    completed_at: datetime | None


class TransactionOut(BaseModel):
    id: uuid.UUID
    receipt: str
    source: str
    amount: AmountStr
    paid_at: datetime | None
    payer: str | None
    bill_reference: str | None
    status: str
    invoice_id: uuid.UUID | None
    payment_id: uuid.UUID | None
    note: str | None
    created_at: datetime


class MatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: uuid.UUID
    invoice_id: uuid.UUID | None = Field(
        default=None, description="Omit to keep it as the client's credit (applied oldest first)"
    )


class IgnoreIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=300)]
