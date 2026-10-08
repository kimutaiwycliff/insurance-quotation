"""M-Pesa Daraja collection (ADR-0015): the tenant's connection, payment prompts, transactions, webhooks."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Audited, Base, MoneyColumn, TenantScoped, Versioned


class MpesaConnection(TenantScoped, Audited, Versioned, Base):
    """The tenant's own Paybill or Till and Daraja app. Money goes straight to it; we only orchestrate."""

    __tablename__ = "mpesa_connections"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id"),  # one connection per tenant for now
        Index("uq_mpesa_connections_callback", "callback_token_hash", unique=True),
    )

    environment: Mapped[str]  # sandbox | production | simulator
    shortcode_type: Mapped[str]  # paybill | till
    business_shortcode: Mapped[str]
    party_b: Mapped[str]
    consumer_key_enc: Mapped[str]
    consumer_secret_enc: Mapped[str]
    passkey_enc: Mapped[str]
    callback_token_hash: Mapped[str]  # sha256 of the secret path segment in callback URLs (lookup)
    callback_token_enc: Mapped[str]  # the segment itself, encrypted (to build callback URLs)
    status: Mapped[str] = mapped_column(server_default="active")  # active | disabled
    c2b_registered_at: Mapped[datetime | None]
    last_error: Mapped[str | None]


class MpesaRequest(TenantScoped, Base):
    """A payment prompt (STK Push) sent to a client's phone."""

    __tablename__ = "mpesa_requests"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "connection_id"], ["mpesa_connections.tenant_id", "mpesa_connections.id"]
        ),
        Index("uq_mpesa_requests_checkout", "tenant_id", "checkout_request_id", unique=True),
        Index("ix_mpesa_requests_status", "tenant_id", "status", "created_at"),
    )

    connection_id: Mapped[uuid.UUID]
    invoice_id: Mapped[uuid.UUID | None]
    phone: Mapped[str]  # E.164
    amount: Mapped[Decimal] = mapped_column(MoneyColumn)  # whole shillings
    account_reference: Mapped[str]
    merchant_request_id: Mapped[str | None]
    checkout_request_id: Mapped[str | None]
    status: Mapped[str] = mapped_column(
        server_default="pending"
    )  # pending|paid|cancelled|failed|expired
    result_code: Mapped[int | None]
    result_desc: Mapped[str | None]
    receipt: Mapped[str | None]
    payment_id: Mapped[uuid.UUID | None]
    source: Mapped[str]  # app | link
    requested_by: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None]


class MpesaTransaction(TenantScoped, Base):
    """Money received on the shortcode (STK or Paybill/Till), matched to an invoice or queued for review."""

    __tablename__ = "mpesa_transactions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "connection_id"], ["mpesa_connections.tenant_id", "mpesa_connections.id"]
        ),
        Index("uq_mpesa_transactions_receipt", "tenant_id", "receipt", unique=True),
        Index("ix_mpesa_transactions_status", "tenant_id", "status"),
    )

    connection_id: Mapped[uuid.UUID]
    receipt: Mapped[str]  # M-Pesa transaction id, e.g. SJK12AB34C
    source: Mapped[str]  # stk | c2b
    amount: Mapped[Decimal] = mapped_column(MoneyColumn)
    paid_at: Mapped[datetime | None]
    payer: Mapped[str | None]  # name or masked number as sent by Safaricom
    bill_reference: Mapped[str | None]
    status: Mapped[str]  # matched | unmatched | ignored
    invoice_id: Mapped[uuid.UUID | None]
    payment_id: Mapped[uuid.UUID | None]
    request_id: Mapped[uuid.UUID | None]
    note: Mapped[str | None]
    resolved_by: Mapped[str | None]
    resolved_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class WebhookEvent(TenantScoped, Base):
    """Every callback, stored before it is acted on (replayable, idempotent per provider key)."""

    __tablename__ = "webhook_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        Index("uq_webhook_events_key", "tenant_id", "provider", "kind", "event_key", unique=True),
    )

    provider: Mapped[str]  # mpesa
    kind: Mapped[str]  # stk_callback | c2b_confirmation
    event_key: Mapped[str]
    connection_id: Mapped[uuid.UUID | None]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    processed_at: Mapped[datetime | None]
    error: Mapped[str | None]
    attempts: Mapped[int] = mapped_column(server_default=text("0"))
