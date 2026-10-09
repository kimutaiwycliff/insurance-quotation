"""Request/response models for invoices, credit notes and payments."""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

from app.core.money import AmountStr, RateStr
from app.core.schema import ExtensibleEnum
from app.modules.quotes.service import ClientRef

Note = Annotated[str, StringConstraints(max_length=3000)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=500)]
Method = Literal["mpesa", "bank", "card", "cheque", "cash", "other"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LineInput(_Strict):
    item_id: uuid.UUID | None = None
    description: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
        | None
    ) = Field(default=None, description="Defaults to the item's name")
    quantity: AmountStr = Field(gt=0)
    unit_price: AmountStr | None = Field(
        default=None, ge=0, description="Defaults to the item's price"
    )
    discount_rate: RateStr = Field(default=0, description="Fraction, e.g. 0.1 = 10% off")  # type: ignore[assignment]
    tax_code: Annotated[str, StringConstraints(max_length=40)] | None = Field(
        default=None, description="Defaults to the item's tax code"
    )
    section: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = (
        Field(default=None, description="Quotes: the heading this line sits under")
    )
    optional: bool = Field(
        default=False, description="Quotes only: an add-on the client may choose; not in the total"
    )

    @model_validator(mode="after")
    def _item_or_details(self) -> LineInput:
        if self.item_id is None and (
            self.description is None or self.unit_price is None or self.tax_code is None
        ):
            raise ValueError("Without an item, give a description, unit price and tax code")
        return self


class _Document(_Strict):
    lines: list[LineInput] = Field(min_length=1, max_length=200)
    prices_include_tax: bool = False
    reference: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] | None = None
    notes: Note | None = None
    terms: Note | None = None


class InvoiceCreate(_Document):
    client_id: uuid.UUID
    due_in_days: Annotated[int, Field(ge=0, le=365)] = 14


class SalesQuoteCreate(_Document):
    client_id: uuid.UUID
    valid_days: Annotated[int, Field(ge=1, le=180)] = 30


class InvoiceUpdate(_Strict):
    lines: list[LineInput] | None = Field(default=None, min_length=1, max_length=200)
    prices_include_tax: bool | None = None
    reference: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] | None = None
    notes: Note | None = None
    terms: Note | None = None
    due_in_days: Annotated[int, Field(ge=0, le=365)] | None = None
    valid_days: Annotated[int, Field(ge=1, le=180)] | None = Field(
        default=None, description="Quotes: validity from today"
    )


class CreditNoteCreate(_Strict):
    invoice_id: uuid.UUID
    reason: Reason
    lines: list[LineInput] | None = Field(
        default=None, max_length=200, description="Omit to credit the whole invoice"
    )


class EtimsIn(_Strict):
    """What the tenant's own eTIMS tool returned for this document (ADR-0017)."""

    cu_invoice_number: Annotated[
        str,
        StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z0-9/-]{6,50}$"),
    ] = Field(description="The KRA control-unit (CU) invoice number")
    verification_url: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None
    ) = Field(
        default=None,
        description="The KRA verification link behind the QR code (https://…kra.go.ke/…)",
    )


class Issue(_Strict):
    issue_date: date | None = Field(default=None, description="Defaults to today")


class Void(_Strict):
    reason: Reason


class Send(_Strict):
    email: EmailStr | None = None
    message: Annotated[str, StringConstraints(max_length=2000)] = ""


class PaymentAllocationIn(_Strict):
    invoice_id: uuid.UUID
    amount: AmountStr = Field(gt=0)


class PaymentCreate(_Strict):
    client_id: uuid.UUID
    amount: AmountStr = Field(gt=0)
    received_on: date
    method: Method = "mpesa"
    reference: Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None = None
    notes: Note | None = None
    allocations: list[PaymentAllocationIn] | None = Field(
        default=None,
        max_length=100,
        description="Omit to apply the payment to the client's open invoices, oldest first",
    )


class BillingLineOut(BaseModel):
    position: int
    item_id: uuid.UUID | None
    description: str
    quantity: AmountStr
    unit_price: AmountStr
    discount_rate: str
    tax_code: str
    section: str | None
    optional: bool
    tax_rate: str
    net: AmountStr
    tax: AmountStr
    total: AmountStr


class TaxLine(BaseModel):
    code: str
    name: str
    rate: str
    taxable: AmountStr
    tax: AmountStr


class PaymentAllocationOut(BaseModel):
    id: uuid.UUID
    invoice_id: uuid.UUID
    invoice_number: str | None
    source: Literal["payment", "credit_note"]
    source_id: uuid.UUID
    source_number: str | None
    amount: AmountStr
    created_at: datetime


Status = Annotated[
    str,
    ExtensibleEnum(
        "draft",
        "open",
        "partially_paid",
        "paid",
        "overdue",
        "issued",
        "sent",
        "accepted",
        "declined",
        "expired",
        "invoiced",
        "void",
    ),
]
Kind = Annotated[str, ExtensibleEnum("invoice", "credit_note", "quote")]


class BillingDocumentSummary(BaseModel):
    id: uuid.UUID
    kind: Kind
    number: str | None
    client: ClientRef
    status: Status = Field(
        description="Invoices: draft, open, partially_paid, paid, overdue or void. "
        "Credit notes: draft, issued or void. "
        "Quotes: draft, sent, accepted, declined, expired, invoiced or void."
    )
    currency: str
    issue_date: date | None
    due_date: date | None
    valid_until: date | None
    total: AmountStr
    paid: AmountStr = Field(description="Allocated to an invoice, or applied from a credit note")
    balance: AmountStr
    etims_cu_invoice_number: str | None
    created_at: datetime


class BillingDocumentOut(BillingDocumentSummary):
    lines: list[BillingLineOut]
    subtotal: AmountStr
    discount: AmountStr
    tax: AmountStr
    taxes: list[TaxLine]
    prices_include_tax: bool
    payment_reference: str | None
    credits_document_id: uuid.UUID | None
    reference: str | None
    notes: str | None
    terms: str | None
    issued_at: datetime | None
    voided_at: datetime | None
    void_reason: str | None
    allocations: list[PaymentAllocationOut]
    credit_notes: list[uuid.UUID] = Field(description="Credit notes issued against this invoice")
    document_id: uuid.UUID | None
    optional_total: AmountStr = Field(
        description="Quotes: the add-ons, if the client takes them all"
    )
    response_status: str | None
    responded_at: datetime | None
    response: dict[str, Any]
    converted_document_id: uuid.UUID | None
    etims_verification_url: str | None
    etims_recorded_at: datetime | None
    version: int


class ReceivedPayment(BaseModel):
    id: uuid.UUID
    number: str
    client: ClientRef
    received_on: date
    amount: AmountStr
    currency: str
    method: str
    reference: str | None
    notes: str | None
    unallocated: AmountStr
    allocations: list[PaymentAllocationOut]
    voided_at: datetime | None
    void_reason: str | None
    created_at: datetime


class ClientAccount(BaseModel):
    client: ClientRef
    currency: str
    owed: AmountStr = Field(description="Receivable: open invoice balances (from the ledger)")
    credit: AmountStr = Field(description="Paid or credited but not yet applied to an invoice")
    open_invoices: list[BillingDocumentSummary]


class DocumentSent(BaseModel):
    document: BillingDocumentOut
    url: str
    emailed_to: str | None
    whatsapp_url: str | None


class FileLink(BaseModel):
    url: str


class AgeingBucket(BaseModel):
    label: str
    amount: AmountStr
    count: int


class MonthBilling(BaseModel):
    month: str = Field(description="YYYY-MM")
    invoiced: AmountStr
    collected: AmountStr


class BillingSummary(BaseModel):
    currency: str
    outstanding: AmountStr
    overdue: AmountStr
    overdue_count: int
    ageing: list[AgeingBucket]
    invoiced_this_month: AmountStr
    collected_this_month: AmountStr
    etims_pending: int = Field(
        description="Issued invoices and credit notes without an eTIMS CU number"
    )
    quotes_awaiting: int
    quotes_awaiting_total: AmountStr
    months: list[MonthBilling]


class QuoteAccept(BaseModel):
    """What the client sends from the link to accept a sales quote."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)] | None = None
    email: EmailStr | None = None
    addons: list[Annotated[int, Field(ge=1, le=200)]] = Field(
        default_factory=list, description="Positions of the optional lines the client wants"
    )
    agree_terms: Literal[True]
    option: None = None


class QuoteDecline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] = ""
