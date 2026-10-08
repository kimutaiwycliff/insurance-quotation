"""Request/response models for commission tracking."""

import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.core.money import AmountStr

Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AllocationIn(_Strict):
    policy_id: uuid.UUID
    gross: AmountStr = Field(gt=0, description="Gross commission the insurer paid for this policy")
    wht: AmountStr | None = Field(
        default=None, ge=0, description="As on the insurer's statement; defaults to the pack rate"
    )


class ReceiptCreate(_Strict):
    insurer_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
    ]
    received_on: date
    reference: Text | None = None
    wht_certificate: Text | None = Field(default=None, description="KRA WHT certificate number")
    notes: Annotated[str, StringConstraints(max_length=2000)] | None = None
    lines: list[AllocationIn] = Field(min_length=1, max_length=500)


class VoidReceipt(_Strict):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=500)]


class AllocationOut(BaseModel):
    policy_id: uuid.UUID
    client_name: str
    description: str
    policy_number: str | None
    gross: AmountStr
    wht: AmountStr
    vat: AmountStr
    net: AmountStr


class ReceiptOut(BaseModel):
    id: uuid.UUID
    insurer_name: str
    received_on: date
    currency: str
    gross: AmountStr
    wht: AmountStr
    vat: AmountStr
    net: AmountStr
    reference: str | None
    wht_certificate: str | None
    notes: str | None
    voided_at: datetime | None
    void_reason: str | None
    created_by: str | None
    created_at: datetime
    lines: list[AllocationOut]


class Amounts(BaseModel):
    gross: AmountStr
    wht: AmountStr
    net: AmountStr


class StatementRow(BaseModel):
    policy_id: uuid.UUID
    client_name: str
    description: str
    insurer_name: str
    policy_number: str | None
    start_date: date
    status: str
    currency: str
    rate: str | None
    expected: Amounts
    received: Amounts
    outstanding: Amounts = Field(description="Expected less received; negative when overpaid")


class Statement(BaseModel):
    currency: str
    rows: list[StatementRow]
    expected_net: AmountStr
    received_net: AmountStr
    outstanding_net: AmountStr


class MonthRow(BaseModel):
    month: str
    expected_net: AmountStr
    received_net: AmountStr
    wht: AmountStr


class InsurerRow(BaseModel):
    insurer_name: str
    expected_net: AmountStr
    received_net: AmountStr
    outstanding_net: AmountStr
    wht: AmountStr


class WhtCertificate(BaseModel):
    receipt_id: uuid.UUID
    insurer_name: str
    received_on: date
    wht: AmountStr
    certificate: str | None


class Summary(BaseModel):
    year: int
    currency: str
    expected_net: AmountStr = Field(description="On policies that started in the year")
    received_net: AmountStr = Field(description="Received in the year")
    outstanding_net: AmountStr = Field(description="All years: expected less received")
    wht: AmountStr = Field(
        description="Withheld by insurers in the year (a credit against income tax)"
    )
    months: list[MonthRow]
    insurers: list[InsurerRow]
    wht_certificates: list[WhtCertificate] = Field(
        description="Receipts with WHT in the year; empty for members who see only their own"
    )
