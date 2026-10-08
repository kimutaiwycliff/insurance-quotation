"""Invoices and credit notes (ADR-0009), payments received and their allocation to invoices."""

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

from app.core.models import Audited, Base, MoneyColumn, RateColumn, TenantScoped, Versioned


class BillingDocument(TenantScoped, Audited, Versioned, Base):
    __tablename__ = "billing_documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(["tenant_id", "client_id"], ["clients.tenant_id", "clients.id"]),
        ForeignKeyConstraint(["tenant_id", "document_id"], ["documents.tenant_id", "documents.id"]),
        ForeignKeyConstraint(
            ["tenant_id", "credits_document_id"],
            ["billing_documents.tenant_id", "billing_documents.id"],
        ),
        Index("uq_billing_documents_number", "tenant_id", "kind", "number", unique=True),
        Index(
            "uq_billing_documents_payment_reference", "tenant_id", "payment_reference", unique=True
        ),
        Index("ix_billing_documents_client", "tenant_id", "client_id", "kind", "status"),
        Index("ix_billing_documents_due", "tenant_id", "status", "due_date"),
        CheckConstraint("kind IN ('invoice', 'credit_note')", name="kind"),
        CheckConstraint("status IN ('draft', 'issued', 'void')", name="status"),
    )

    kind: Mapped[str]
    number: Mapped[str | None]  # allocated at issue
    client_id: Mapped[uuid.UUID]
    owner_user_id: Mapped[str]
    status: Mapped[str] = mapped_column(server_default="draft")
    currency: Mapped[str] = mapped_column(CHAR(3))
    issue_date: Mapped[date | None]
    due_date: Mapped[date | None]
    prices_include_tax: Mapped[bool] = mapped_column(server_default=text("false"))
    subtotal: Mapped[Decimal] = mapped_column(MoneyColumn, server_default="0")
    discount: Mapped[Decimal] = mapped_column(MoneyColumn, server_default="0")
    tax: Mapped[Decimal] = mapped_column(MoneyColumn, server_default="0")
    total: Mapped[Decimal] = mapped_column(MoneyColumn, server_default="0")
    taxes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    pack: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    payment_reference: Mapped[str | None]  # short M-Pesa account reference (ADR-0010)
    credits_document_id: Mapped[uuid.UUID | None]  # a credit note's invoice
    reference: Mapped[str | None]  # the client's PO or order number
    notes: Mapped[str | None]
    terms: Mapped[str | None]
    document_id: Mapped[uuid.UUID | None]  # PDF of the issued document
    issued_at: Mapped[datetime | None]
    issued_by: Mapped[str | None]
    voided_at: Mapped[datetime | None]
    void_reason: Mapped[str | None]


class BillingLine(TenantScoped, Base):
    __tablename__ = "billing_lines"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "document_id", "position"),
        ForeignKeyConstraint(
            ["tenant_id", "document_id"], ["billing_documents.tenant_id", "billing_documents.id"]
        ),
        ForeignKeyConstraint(["tenant_id", "item_id"], ["items.tenant_id", "items.id"]),
    )

    document_id: Mapped[uuid.UUID]
    position: Mapped[int]
    item_id: Mapped[uuid.UUID | None]
    description: Mapped[str]
    quantity: Mapped[Decimal] = mapped_column(MoneyColumn)
    unit_price: Mapped[Decimal] = mapped_column(MoneyColumn)
    discount_rate: Mapped[Decimal] = mapped_column(RateColumn, server_default="0")
    tax_code: Mapped[str]
    tax_rate: Mapped[Decimal] = mapped_column(RateColumn)
    net: Mapped[Decimal] = mapped_column(MoneyColumn)
    tax: Mapped[Decimal] = mapped_column(MoneyColumn)
    total: Mapped[Decimal] = mapped_column(MoneyColumn)


class Payment(TenantScoped, Base):
    """Money a client paid the tenant (into the tenant's own account). Voided, never edited or deleted."""

    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(["tenant_id", "client_id"], ["clients.tenant_id", "clients.id"]),
        ForeignKeyConstraint(["tenant_id", "document_id"], ["documents.tenant_id", "documents.id"]),
        Index("uq_payments_number", "tenant_id", "number", unique=True),
        Index("ix_payments_client", "tenant_id", "client_id"),
        CheckConstraint("amount > 0", name="amount"),
    )

    number: Mapped[str]  # receipt number
    client_id: Mapped[uuid.UUID]
    received_on: Mapped[date]
    amount: Mapped[Decimal] = mapped_column(MoneyColumn)
    currency: Mapped[str] = mapped_column(CHAR(3))
    method: Mapped[str]  # mpesa | bank | card | cheque | cash | other
    reference: Mapped[str | None]  # M-Pesa code, cheque number...
    notes: Mapped[str | None]
    document_id: Mapped[uuid.UUID | None]  # receipt PDF
    voided_at: Mapped[datetime | None]
    void_reason: Mapped[str | None]
    voided_by: Mapped[str | None]
    created_by: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Allocation(TenantScoped, Base):
    """Part of a payment or a credit note applied to an invoice (append-only)."""

    __tablename__ = "allocations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(["tenant_id", "payment_id"], ["payments.tenant_id", "payments.id"]),
        ForeignKeyConstraint(
            ["tenant_id", "credit_note_id"],
            ["billing_documents.tenant_id", "billing_documents.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "invoice_id"], ["billing_documents.tenant_id", "billing_documents.id"]
        ),
        Index("ix_allocations_invoice", "tenant_id", "invoice_id"),
        Index("ix_allocations_payment", "tenant_id", "payment_id"),
        Index("ix_allocations_credit_note", "tenant_id", "credit_note_id"),
        CheckConstraint("amount > 0", name="amount"),
        CheckConstraint("(payment_id IS NULL) <> (credit_note_id IS NULL)", name="one_source"),
    )

    payment_id: Mapped[uuid.UUID | None]
    credit_note_id: Mapped[uuid.UUID | None]
    invoice_id: Mapped[uuid.UUID]
    amount: Mapped[Decimal] = mapped_column(MoneyColumn)
    created_by: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
