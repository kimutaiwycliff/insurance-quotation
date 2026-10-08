"""Insurance quotes: a client, a risk and one or more insurer options, each a frozen calculation snapshot."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CHAR, ForeignKeyConstraint, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Audited, Base, MoneyColumn, TenantScoped, Versioned


class Quote(TenantScoped, Audited, Versioned, Base):
    __tablename__ = "quotes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(["tenant_id", "client_id"], ["clients.tenant_id", "clients.id"]),
        ForeignKeyConstraint(["tenant_id", "document_id"], ["documents.tenant_id", "documents.id"]),
        Index("uq_quotes_number", "tenant_id", "number", unique=True),
        Index("ix_quotes_client", "tenant_id", "client_id"),
        Index("ix_quotes_owner_status", "tenant_id", "owner_user_id", "status"),
    )

    number: Mapped[str | None]  # allocated when first sent
    client_id: Mapped[uuid.UUID]
    owner_user_id: Mapped[str]
    class_code: Mapped[str]
    title: Mapped[str]
    currency: Mapped[str] = mapped_column(CHAR(3), server_default="KES")
    status: Mapped[str] = mapped_column(
        server_default="draft"
    )  # draft|sent|accepted|declined|withdrawn
    risk: Mapped[dict[str, Any]] = mapped_column(
        JSONB
    )  # RiskIn snapshot (sum insured, members, benefits...)
    details: Mapped[list[dict[str, str]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    notes: Mapped[str | None]
    valid_until: Mapped[date]
    sent_at: Mapped[datetime | None]
    document_id: Mapped[uuid.UUID | None]  # latest PDF
    accepted_position: Mapped[int | None]
    responded_at: Mapped[datetime | None]
    # Acceptance evidence (KICA): name, contact, terms agreed, hashed IP, user agent, timestamp.
    response: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class QuoteOption(TenantScoped, Base):
    __tablename__ = "quote_options"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "quote_id", "position"),
        ForeignKeyConstraint(["tenant_id", "quote_id"], ["quotes.tenant_id", "quotes.id"]),
        ForeignKeyConstraint(["tenant_id", "product_id"], ["products.tenant_id", "products.id"]),
    )

    quote_id: Mapped[uuid.UUID]
    position: Mapped[int]
    product_id: Mapped[uuid.UUID]
    insurer_name: Mapped[str]
    product_name: Mapped[str]
    excess_text: Mapped[str | None]
    # Client-facing breakdown (lines, totals, pack version, notes) frozen at calculation time.
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB)
    client_total: Mapped[Decimal] = mapped_column(MoneyColumn)
    # Internal only: never serialised into anything a client sees.
    commission: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    needs_input: Mapped[bool] = mapped_column(server_default=text("false"))
    recommended: Mapped[bool] = mapped_column(server_default=text("false"))
