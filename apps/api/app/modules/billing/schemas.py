"""Request/response models for invoices, credit notes and payments."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

from app.core.money import AmountStr, RateStr
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


class InvoiceUpdate(_Strict):
    lines: list[LineInput] | None = Field(default=None, min_length=1, max_length=200)
    prices_include_tax: bool | None = None
    reference: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] | None = None
    notes: Note | None = None
    terms: Note | None = None
    due_in_days: Annotated[int, Field(ge=0, le=365)] | None = None


class CreditNoteCreate(_Strict):
    invoice_id: uuid.UUID
    reason: Reason
    lines: list[LineInput] | None = Field(
        default=None, max_length=200, description="Omit to credit the whole invoice"
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


Status = Literal["draft", "open", "partially_paid", "paid", "overdue", "issued", "void"]


class BillingDocumentSummary(BaseModel):
    id: uuid.UUID
    kind: Literal["invoice", "credit_note"]
    number: str | None
    client: ClientRef
    status: Status = Field(
        description="Invoices: draft, open, partially_paid, paid, overdue or void. "
        "Credit notes: draft, issued or void."
    )
    currency: str
    issue_date: date | None
    due_date: date | None
    total: AmountStr
    paid: AmountStr = Field(description="Allocated to an invoice, or applied from a credit note")
    balance: AmountStr
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
