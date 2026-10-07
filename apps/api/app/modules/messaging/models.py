"""Outbound message log, tenant template overrides and the suppression list."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Audited, Base, TenantScoped, Versioned


class OutboundMessage(TenantScoped, Base):
    __tablename__ = "outbound_messages"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        Index("ix_outbound_messages_entity", "tenant_id", "entity_type", "entity_id"),
    )

    channel: Mapped[str] = mapped_column(server_default="email")
    stream: Mapped[str]  # transactional | reminders
    event: Mapped[str]
    to_address: Mapped[str] = mapped_column(CITEXT)
    subject: Mapped[str]
    body_text: Mapped[str]
    body_html: Mapped[str | None]
    status: Mapped[str] = mapped_column(
        server_default="queued"
    )  # queued | sent | failed | suppressed
    attempts: Mapped[int] = mapped_column(server_default=text("0"))
    provider_message_id: Mapped[str | None]
    error: Mapped[str | None]
    entity_type: Mapped[str | None]
    entity_id: Mapped[uuid.UUID | None]
    created_by: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    sent_at: Mapped[datetime | None]


class MessageTemplate(TenantScoped, Audited, Versioned, Base):
    """A tenant's override of a built-in message template (deleting it restores the default)."""

    __tablename__ = "message_templates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "event", "channel", "locale"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )

    event: Mapped[str]
    channel: Mapped[str] = mapped_column(server_default="email")
    locale: Mapped[str] = mapped_column(server_default="en")
    subject: Mapped[str]
    body: Mapped[str]


class EmailSuppression(TenantScoped, Base):
    __tablename__ = "email_suppressions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "email", "stream"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )

    email: Mapped[str] = mapped_column(CITEXT)
    stream: Mapped[str]
    reason: Mapped[str]  # unsubscribed | bounced | complaint
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
