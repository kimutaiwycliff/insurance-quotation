"""Request/response models for plans and subscriptions."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.core.money import AmountStr


class PlanPrice(BaseModel):
    cycle: Literal["monthly", "yearly"]
    list_price: AmountStr
    price: AmountStr = Field(description="What you would pay now (founding discount applied)")
    discount_percent: int


class PlanOut(BaseModel):
    code: str
    name: str
    tagline: str
    included_seats: int
    extra_seat_monthly: AmountStr | None
    features: list[str]
    limits: dict[str, int]
    prices: list[PlanPrice]


class Usage(BaseModel):
    clients: int
    documents_this_month: int
    seats_used: int


class SubscriptionOut(BaseModel):
    plan: str
    plan_name: str
    paid_plan: str
    status: str = Field(description="trialing, active, past_due, read_only or free")
    billing_cycle: str
    trial_ends_at: datetime | None
    period_end: date | None
    seats: int
    founding_member: bool
    discount_percent: int
    discount_until: date | None
    features: list[str]
    limits: dict[str, int]
    usage: Usage
    founding_places_left: int


class Checkout(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: Literal["agent", "agency", "business"]
    cycle: Literal["monthly", "yearly"] = "monthly"
    extra_seats: Annotated[int, Field(ge=0, le=100)] = 0
    phone: Annotated[str, StringConstraints(strip_whitespace=True, min_length=9, max_length=20)]


class SubscriptionPaymentOut(BaseModel):
    id: uuid.UUID
    plan: str
    billing_cycle: str
    extra_seats: int
    list_price: AmountStr
    discount_percent: int
    amount: AmountStr
    status: str = Field(description="pending, paid, cancelled, failed or expired")
    receipt: str | None
    result_desc: str | None
    period_start: date | None
    period_end: date | None
    created_at: datetime
    completed_at: datetime | None
