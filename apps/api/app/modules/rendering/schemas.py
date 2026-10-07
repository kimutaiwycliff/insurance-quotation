"""Request/response models for templates and branding."""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modules.rendering.fixtures import Variant
from app.modules.rendering.view import DocType, HexColor

Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]


class TemplateOut(BaseModel):
    key: str
    name: str
    description: str
    tier: Literal["free", "premium"]
    version: int
    doc_types: list[str]
    paper: str
    font_pair: str


class PaymentDefaults(BaseModel):
    """Payment instructions printed on invoices (the per-document reference is added automatically)."""

    model_config = ConfigDict(extra="forbid")

    mpesa_paybill: Annotated[str, StringConstraints(pattern=r"^\d{5,7}$")] | None = None
    mpesa_till: Annotated[str, StringConstraints(pattern=r"^\d{5,7}$")] | None = None
    bank_name: Text | None = None
    bank_account_name: Text | None = None
    bank_account_number: (
        Annotated[str, StringConstraints(pattern=r"^[0-9A-Za-z -]{4,34}$")] | None
    ) = None
    bank_branch: Text | None = None
    swift_code: Annotated[str, StringConstraints(pattern=r"^[A-Z0-9]{8}([A-Z0-9]{3})?$")] | None = (
        None
    )


class BrandingOut(BaseModel):
    templates: dict[str, str] = Field(description="Template key per document type (effective)")
    primary_color: str | None
    accent_color: str | None
    font_pair: str | None
    logo_document_id: uuid.UUID | None
    footer_text: str | None
    payment_instructions: PaymentDefaults
    version: int


class BrandingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    templates: dict[DocType, str] | None = None
    primary_color: HexColor | None = None
    accent_color: HexColor | None = None
    font_pair: Literal["sans", "serif"] | None = None
    logo_document_id: uuid.UUID | None = None
    footer_text: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = (
        None
    )
    payment_instructions: PaymentDefaults | None = None


class TemplatePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_type: DocType = "invoice"
    format: Literal["pdf", "html"] = "pdf"
    variant: Variant = "standard"
    # Unsaved branding to try out (the settings screen's live preview); defaults to the saved branding.
    branding: BrandingUpdate | None = None
