"""Policy book: policies the agent placed with insurers, premium payments recorded against them, renewal work."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Audited, Base, MoneyColumn, TenantScoped, Versioned


class Policy(TenantScoped, Audited, Versioned, Base):
    __tablename__ = "policies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(["tenant_id", "client_id"], ["clients.tenant_id", "clients.id"]),
        ForeignKeyConstraint(["tenant_id", "quote_id"], ["quotes.tenant_id", "quotes.id"]),
        ForeignKeyConstraint(["tenant_id", "product_id"], ["products.tenant_id", "products.id"]),
        ForeignKeyConstraint(
            ["tenant_id", "renewed_from_id"], ["policies.tenant_id", "policies.id"]
        ),
        Index("uq_policies_quote", "tenant_id", "quote_id", unique=True),
        Index("uq_policies_renewed_from", "tenant_id", "renewed_from_id", unique=True),
        Index("ix_policies_client", "tenant_id", "client_id"),
        Index("ix_policies_owner_end", "tenant_id", "owner_user_id", "end_date"),
        Index("ix_policies_end", "tenant_id", "end_date"),
        CheckConstraint("end_date > start_date", name="dates"),
        CheckConstraint("total_premium >= 0", name="premium"),
    )

    client_id: Mapped[uuid.UUID]
    owner_user_id: Mapped[str]
    quote_id: Mapped[uuid.UUID | None]  # the accepted quote it came from
    product_id: Mapped[uuid.UUID | None]
    insurer_name: Mapped[str]
    product_name: Mapped[str]
    class_code: Mapped[str]
    policy_number: Mapped[str | None]  # the insurer's number (unknown until the insurer issues it)
    description: Mapped[str]  # e.g. "KDA 123A Toyota Axio" or "Family medical: 4 members"
    details: Mapped[list[dict[str, str]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    status: Mapped[str] = mapped_column(server_default="pending")  # pending|active|cancelled
    start_date: Mapped[date]
    end_date: Mapped[date]
    currency: Mapped[str] = mapped_column(CHAR(3), server_default="KES")
    sum_insured: Mapped[Decimal | None] = mapped_column(MoneyColumn)
    total_premium: Mapped[Decimal] = mapped_column(
        MoneyColumn
    )  # what the client pays, levies included
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    commission: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # expected; internal only
    # insurer_direct: the client pays the insurer. agent_collected: the agent receives it and must remit
    # immediately (Regs r.42). The platform never holds the money in either case.
    collection_mode: Mapped[str] = mapped_column(server_default="insurer_direct")
    activated_at: Mapped[datetime | None]
    activation: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    cancelled_at: Mapped[datetime | None]
    cancel_reason: Mapped[str | None]
    renewed_from_id: Mapped[uuid.UUID | None]
    # due|contacted|quoted|renewed|lost: where renewal work stands for this policy.
    renewal_stage: Mapped[str] = mapped_column(server_default="due")
    renewal_quote_id: Mapped[uuid.UUID | None]
    renewed_to_id: Mapped[uuid.UUID | None]
    lost_reason: Mapped[str | None]
    last_contacted_at: Mapped[datetime | None]
    notes: Mapped[str | None]


class PolicyPayment(TenantScoped, Base):
    """A premium payment the agent records (to the insurer, or to the agent when authorised).

    Payments are never deleted or changed: a wrong entry is voided with a reason and entered again.
    """

    __tablename__ = "policy_payments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(["tenant_id", "policy_id"], ["policies.tenant_id", "policies.id"]),
        Index("ix_policy_payments_policy", "tenant_id", "policy_id"),
        CheckConstraint("amount > 0", name="amount"),
    )

    policy_id: Mapped[uuid.UUID]
    amount: Mapped[Decimal] = mapped_column(MoneyColumn)
    currency: Mapped[str] = mapped_column(CHAR(3))
    paid_on: Mapped[date]
    method: Mapped[str]  # mpesa|bank|card|cheque|cash|other
    reference: Mapped[str | None]  # M-Pesa code, cheque number...
    paid_to: Mapped[str]  # insurer|agent
    remit_task_id: Mapped[uuid.UUID | None]
    remitted_on: Mapped[date | None]
    remittance_reference: Mapped[str | None]
    voided_at: Mapped[datetime | None]
    void_reason: Mapped[str | None]
    voided_by: Mapped[str | None]
    created_by: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class RenewalReminder(TenantScoped, Base):
    """One row per reminder sent, so the daily job never reminds twice for the same offset."""

    __tablename__ = "renewal_reminders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "policy_id", "offset_days"),
        ForeignKeyConstraint(["tenant_id", "policy_id"], ["policies.tenant_id", "policies.id"]),
    )

    policy_id: Mapped[uuid.UUID]
    offset_days: Mapped[int]
    emailed_to: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
