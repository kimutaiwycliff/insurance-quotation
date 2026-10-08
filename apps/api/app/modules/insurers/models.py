"""Insurers the agency is appointed with, and their products (rates, minimum premiums, benefits, commission)."""

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import CHAR, ForeignKeyConstraint, Index, Numeric, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Audited, Base, MoneyColumn, TenantScoped, Versioned

RateColumn = Numeric(12, 8, asdecimal=True)  # fractions, e.g. 0.035 = 3.5%


class Insurer(TenantScoped, Audited, Versioned, Base):
    __tablename__ = "insurers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        Index("uq_insurers_name", "tenant_id", "name", unique=True),
    )

    name: Mapped[str] = mapped_column(CITEXT)
    short_name: Mapped[str | None]
    email: Mapped[str | None] = mapped_column(CITEXT)
    phone: Mapped[str | None]
    # Where clients pay this insurer directly (insurer-direct collection, Plan A1).
    mpesa_paybill: Mapped[str | None]
    payment_account_hint: Mapped[str | None]  # e.g. "Use your policy number as the account"
    bank_details: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    notes: Mapped[str | None]
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))


class Product(TenantScoped, Audited, Versioned, Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(["tenant_id", "insurer_id"], ["insurers.tenant_id", "insurers.id"]),
        Index("uq_products_name", "tenant_id", "insurer_id", "name", unique=True),
        Index("ix_products_class", "tenant_id", "class_code"),
    )

    insurer_id: Mapped[uuid.UUID]
    class_code: Mapped[str]
    name: Mapped[str]
    currency: Mapped[str] = mapped_column(CHAR(3), server_default="KES")
    rating_basis: Mapped[str]  # rate_on_sum_insured | flat | per_member | manual
    rate: Mapped[Decimal | None] = mapped_column(RateColumn)
    flat_premium: Mapped[Decimal | None] = mapped_column(MoneyColumn)
    min_premium: Mapped[Decimal] = mapped_column(MoneyColumn, server_default=text("0"))
    # [{code, name, basis, value, optional, selected_by_default, commissionable}]
    benefits: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    # [{label, amount}] for per-member products (e.g. Principal, Spouse, Child)
    member_tiers: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    excess_text: Mapped[str | None]
    commission_rate_new: Mapped[Decimal | None] = mapped_column(RateColumn)
    commission_rate_renewal: Mapped[Decimal | None] = mapped_column(RateColumn)
    notes: Mapped[str | None]
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
