"""Commission received from insurers, allocated to the policies it pays for."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CHAR, CheckConstraint, ForeignKeyConstraint, Index, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, MoneyColumn, TenantScoped


class CommissionReceipt(TenantScoped, Base):
    """One payment from an insurer (usually monthly, with a statement). Voided, never edited or deleted."""

    __tablename__ = "commission_receipts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        Index("ix_commission_receipts_received", "tenant_id", "received_on"),
        CheckConstraint("net >= 0", name="net"),
    )

    insurer_name: Mapped[str]
    received_on: Mapped[date]
    currency: Mapped[str] = mapped_column(CHAR(3))
    gross: Mapped[Decimal] = mapped_column(MoneyColumn)
    wht: Mapped[Decimal] = mapped_column(
        MoneyColumn
    )  # withheld by the insurer, a credit on the agent's tax
    vat: Mapped[Decimal] = mapped_column(MoneyColumn)
    net: Mapped[Decimal] = mapped_column(MoneyColumn)  # what reached the agent's account
    reference: Mapped[str | None]  # bank / M-Pesa reference or statement number
    wht_certificate: Mapped[str | None]  # KRA WHT certificate number from the insurer
    notes: Mapped[str | None]
    voided_at: Mapped[datetime | None]
    void_reason: Mapped[str | None]
    voided_by: Mapped[str | None]
    created_by: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class CommissionAllocation(TenantScoped, Base):
    """The part of a receipt that pays one policy's commission (append-only)."""

    __tablename__ = "commission_allocations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "receipt_id", "policy_id"),
        ForeignKeyConstraint(
            ["tenant_id", "receipt_id"], ["commission_receipts.tenant_id", "commission_receipts.id"]
        ),
        ForeignKeyConstraint(["tenant_id", "policy_id"], ["policies.tenant_id", "policies.id"]),
        Index("ix_commission_allocations_policy", "tenant_id", "policy_id"),
    )

    receipt_id: Mapped[uuid.UUID]
    policy_id: Mapped[uuid.UUID]
    gross: Mapped[Decimal] = mapped_column(MoneyColumn)
    wht: Mapped[Decimal] = mapped_column(MoneyColumn)
    vat: Mapped[Decimal] = mapped_column(MoneyColumn)
    net: Mapped[Decimal] = mapped_column(MoneyColumn)
