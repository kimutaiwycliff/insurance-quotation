"""Tenant branding and template choice per document type."""

import uuid
from typing import Any

from sqlalchemy import ForeignKeyConstraint, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Audited, Base, TenantScoped, Versioned


class BrandingSettings(TenantScoped, Audited, Versioned, Base):
    """One row per tenant (created on first read)."""

    __tablename__ = "branding_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        ForeignKeyConstraint(
            ["tenant_id", "logo_document_id"], ["documents.tenant_id", "documents.id"]
        ),
    )

    # {"quote": "classic", "invoice": "savanna", ...}; missing types use the default template.
    templates: Mapped[dict[str, str]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    primary_color: Mapped[str | None]
    accent_color: Mapped[str | None]
    font_pair: Mapped[str | None]  # sans | serif; None = the template's own
    logo_document_id: Mapped[uuid.UUID | None]
    footer_text: Mapped[str | None]
    # PaymentInstructions without "reference" (that one is per document).
    payment_instructions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
