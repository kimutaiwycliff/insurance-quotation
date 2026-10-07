"""Public document links (token hashed at rest) and their events."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantScoped


class PublicLink(TenantScoped, Base):
    __tablename__ = "public_links"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        # Global uniqueness: a token resolves to exactly one link of one tenant.
        Index("uq_public_links_token_hash", "token_hash", unique=True),
        Index("ix_public_links_entity", "tenant_id", "entity_type", "entity_id"),
    )

    token_hash: Mapped[bytes] = mapped_column(LargeBinary)
    entity_type: Mapped[str]
    entity_id: Mapped[uuid.UUID]
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String))
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    created_by: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    sent_message_id: Mapped[uuid.UUID | None]
    view_count: Mapped[int] = mapped_column(server_default=text("0"))
    last_viewed_at: Mapped[datetime | None]


class LinkEvent(TenantScoped, Base):
    """Append-only: opened, viewed, downloaded, revoked (accepted/paid arrive with quotes and payments)."""

    __tablename__ = "link_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "link_id"], ["public_links.tenant_id", "public_links.id"]
        ),
        Index("ix_link_events_link", "tenant_id", "link_id"),
    )

    link_id: Mapped[uuid.UUID]
    event_type: Mapped[str]
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now())
    ip_hash: Mapped[
        str | None
    ]  # HMAC of the client IP: lets us count distinct viewers without storing IPs
    user_agent: Mapped[str | None]
    is_bot: Mapped[bool] = mapped_column(server_default=text("false"))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
