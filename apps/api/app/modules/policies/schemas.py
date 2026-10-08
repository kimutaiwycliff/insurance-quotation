"""Request/response models for the policy book and renewals."""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.core.money import AmountStr
from app.modules.insurers.service import RiskIn
from app.modules.quotes.service import ClientRef, Detail, QuoteCreate

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Reference = Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)]

CollectionMode = Literal["insurer_direct", "agent_collected"]
Method = Literal["mpesa", "bank", "card", "cheque", "cash", "other"]
PaidTo = Literal["insurer", "agent"]
Status = Literal["pending", "active", "expired", "cancelled"]
RenewalStage = Literal["due", "contacted", "quoted", "renewed", "lost"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PaymentIn(_Strict):
    amount: AmountStr = Field(gt=0)
    paid_on: date
    method: Method = "mpesa"
    reference: Reference | None = None
    paid_to: PaidTo | None = Field(
        default=None, description="Defaults from the policy's collection mode"
    )


class _Cover(_Strict):
    policy_number: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None
    ) = None
    start_date: date
    end_date: date | None = Field(default=None, description="Defaults to one year less a day")
    collection_mode: CollectionMode = "insurer_direct"
    details: list[Detail] | None = Field(default=None, max_length=12)
    notes: Note | None = None
    payment: PaymentIn | None = Field(default=None, description="A payment already made")
    insurer_confirmed: bool = Field(
        default=False,
        description="The insurer has confirmed cover; activates the policy when the premium is paid",
    )

    @model_validator(mode="after")
    def _dates(self) -> _Cover:
        if self.end_date is not None and self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


class FromQuote(_Cover):
    quote_id: uuid.UUID
    option: Annotated[int, Field(ge=1, le=8)] | None = Field(
        default=None,
        description="The option the client took, when they accepted by phone rather than on the link",
    )


class PolicyCreate(_Cover):
    """A policy written outside a quote (e.g. an existing client's cover entered into the book)."""

    client_id: uuid.UUID
    product_id: uuid.UUID | None = None
    insurer_name: Text | None = Field(default=None, description="Required without product_id")
    product_name: Text | None = None
    class_code: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,40}$")] | None = None
    description: Text | None = None
    sum_insured: AmountStr | None = Field(default=None, ge=0)
    total_premium: AmountStr = Field(ge=0)
    renewed_from_id: uuid.UUID | None = None


class PolicyUpdate(_Strict):
    policy_number: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None
    ) = None
    description: Text | None = None
    details: list[Detail] | None = Field(default=None, max_length=12)
    notes: Note | None = None
    start_date: date | None = None
    end_date: date | None = None


class Activate(_Strict):
    basis: Literal["paid", "exception"] = "paid"
    exception_id: Annotated[str, StringConstraints(max_length=80)] | None = None
    insurer_confirmed: Literal[True] = Field(description="The insurer has confirmed cover")
    note: Note = ""


class Cancel(_Strict):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=500)]


class VoidPayment(_Strict):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=500)]


class Remitted(_Strict):
    remitted_on: date
    reference: Reference | None = None


class RenewalUpdate(_Strict):
    stage: Literal["due", "contacted", "lost"]
    lost_reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = (
        None
    )
    note: Note | None = Field(default=None, description="Logged on the client's timeline")


class Remind(_Strict):
    channel: Literal["email", "whatsapp", "call", "sms"]
    message: Annotated[str, StringConstraints(max_length=2000)] | None = None


class RenewalQuote(_Strict):
    """Start a renewal quote from the policy: client, class and details are copied."""

    product_ids: list[uuid.UUID] = Field(min_length=1, max_length=8)
    risk: RiskIn
    recommended_product_id: uuid.UUID | None = None
    details: list[Detail] | None = Field(default=None, max_length=12)
    notes: Note | None = None
    valid_days: Annotated[int, Field(ge=1, le=90)] = 30

    def to_quote(self, client_id: uuid.UUID, details: list[Detail], title: str) -> QuoteCreate:
        return QuoteCreate.model_validate(
            {
                "client_id": client_id,
                "product_ids": self.product_ids,
                "risk": self.risk,
                "recommended_product_id": self.recommended_product_id,
                "details": self.details if self.details is not None else details,
                "notes": self.notes,
                "valid_days": self.valid_days,
                "title": title,
            }
        )


class PaymentOut(BaseModel):
    id: uuid.UUID
    amount: AmountStr
    currency: str
    paid_on: date
    method: str
    reference: str | None
    paid_to: str
    remitted_on: date | None
    remittance_reference: str | None
    voided_at: datetime | None
    void_reason: str | None
    created_by: str | None
    created_at: datetime


class PolicySummary(BaseModel):
    id: uuid.UUID
    client: ClientRef
    policy_number: str | None
    insurer_name: str
    product_name: str
    class_code: str
    description: str
    status: Status = Field(description="'expired' when an active policy is past its end date")
    start_date: date
    end_date: date
    days_to_expiry: int
    currency: str
    total_premium: AmountStr
    paid: AmountStr
    balance: AmountStr
    collection_mode: CollectionMode
    renewal_stage: RenewalStage
    owner_user_id: str


class PremiumExceptionOut(BaseModel):
    id: str
    name: str
    source: str
    note: str


class PolicyOut(PolicySummary):
    quote_id: uuid.UUID | None
    product_id: uuid.UUID | None
    details: list[Detail]
    sum_insured: AmountStr | None
    breakdown: dict[str, Any]
    commission: dict[str, Any] | None = Field(description="Only for roles that may see commission")
    activated_at: datetime | None
    activation: dict[str, Any]
    cancelled_at: datetime | None
    cancel_reason: str | None
    renewed_from_id: uuid.UUID | None
    renewed_to_id: uuid.UUID | None
    renewal_quote_id: uuid.UUID | None
    lost_reason: str | None
    last_contacted_at: datetime | None
    notes: str | None
    payments: list[PaymentOut]
    unremitted: AmountStr = Field(
        description="Premium the agent collected and has not yet remitted"
    )
    premium_exceptions: list[PremiumExceptionOut] = Field(
        description="Cases in which this class may be activated before full payment"
    )
    version: int
    created_at: datetime


class RenewalItem(PolicySummary):
    whatsapp_url: str | None
    last_contacted_at: datetime | None
    renewal_quote_id: uuid.UUID | None
    renewal_quote_status: str | None
    lost_reason: str | None


class RenewalColumn(BaseModel):
    stage: RenewalStage
    count: int
    premium: AmountStr


class RenewalBoard(BaseModel):
    window_days: int
    currency: str
    columns: list[RenewalColumn]
    items: list[RenewalItem]


class Reminded(BaseModel):
    policy: PolicyOut
    whatsapp_url: str | None
    emailed_to: str | None
