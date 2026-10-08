"""The data a document template sees. Modules (quotes, invoices, receipts) build a ``DocumentView``; templates
never touch the database. Every string is escaped by the template engine (autoescape on)."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

DocType = Literal["quote", "invoice", "receipt", "credit_note"]
HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]

DOC_TITLES: dict[str, str] = {
    "quote": "Quotation",
    "invoice": "Invoice",
    "receipt": "Receipt",
    "credit_note": "Credit note",
}


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Party(_Model):
    name: str
    address_lines: list[str] = Field(default_factory=list)
    tax_pin: str | None = None
    email: str | None = None
    phone: str | None = None


class LineItem(_Model):
    description: str
    details: str | None = None
    section: str | None = Field(default=None, description="Heading the line is grouped under")
    optional: bool = Field(
        default=False, description="Quote add-on, listed apart and not in the total"
    )
    quantity: Decimal = Decimal(1)
    unit_price: Decimal
    amount: Decimal


class AmountLine(_Model):
    label: str
    amount: Decimal


class Totals(_Model):
    subtotal: Decimal
    charges: list[AmountLine] = Field(
        default_factory=list, description="Taxes, levies, stamp duty... computed by app/calc"
    )
    total: Decimal
    amount_paid: Decimal | None = None
    balance: Decimal | None = None


class KeyValue(_Model):
    label: str
    value: str


class OptionView(_Model):
    """One insurer's offer in a comparison quote (client-facing: never carries commission)."""

    position: int
    insurer: str
    product: str
    premium: Decimal = Field(description="premium incl. benefits, loadings and discounts")
    charges: list[AmountLine] = Field(default_factory=list, description="levies, stamp duty, fees")
    total: Decimal
    excess: str | None = None
    recommended: bool = False


class PaymentInstructions(_Model):
    reference: str | None = Field(
        default=None, description="Short payment reference (M-Pesa account)"
    )
    mpesa_paybill: str | None = None
    mpesa_till: str | None = None
    bank_name: str | None = None
    bank_account_name: str | None = None
    bank_account_number: str | None = None
    bank_branch: str | None = None
    swift_code: str | None = None


class DocumentView(_Model):
    doc_type: DocType
    number: str | None = Field(default=None, description="None for drafts")
    issue_date: date
    due_date: date | None = None
    valid_until: date | None = None
    reference: str | None = None
    currency: str
    seller: Party
    buyer: Party
    details: list[KeyValue] = Field(
        default_factory=list, description="e.g. vehicle, cover type, period"
    )
    lines: list[LineItem] = Field(default_factory=list)
    totals: Totals | None = None
    options: list[OptionView] = Field(
        default_factory=list, description="comparison quotes: one per insurer"
    )
    notes: str | None = None
    terms: str | None = None
    payment: PaymentInstructions | None = None
    tax_control: list[KeyValue] = Field(default_factory=list, description="eTIMS CU number etc.")
    stamp: Literal["DRAFT", "PAID", "VOID"] | None = None
    locale: str = "en-KE"


class BrandingView(_Model):
    primary_color: HexColor = "#1F4E79"
    accent_color: HexColor = "#E8A33D"
    font_pair: Literal["sans", "serif"] = "sans"
    logo_data_uri: (
        Annotated[
            str, StringConstraints(pattern=r"^data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$")
        ]
        | None
    ) = None
    footer_text: str | None = None
