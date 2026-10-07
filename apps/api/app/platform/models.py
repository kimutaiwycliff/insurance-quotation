"""Platform-owned tables: currencies (global reference data), audit log and idempotency keys."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CHAR, ForeignKey, Index, SmallInteger, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantScoped


class Currency(Base):
    """ISO 4217 currencies (global, read-only to the API). Seeded from ``app.core.money``."""

    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(CHAR(3), primary_key=True)
    name: Mapped[str]
    minor_unit: Mapped[int] = mapped_column(SmallInteger)


class AuditEvent(TenantScoped, Base):
    """Append-only record of who changed what (``app_user`` has no UPDATE/DELETE grant)."""

    __tablename__ = "audit_events"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now())
    actor_type: Mapped[str]  # user | service | system
    actor_id: Mapped[str | None]
    action: Mapped[str]  # e.g. "branch.created"
    entity_type: Mapped[str]
    entity_id: Mapped[str | None]
    request_id: Mapped[str | None]
    changes: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")


Index("ix_audit_events_entity", AuditEvent.tenant_id, AuditEvent.entity_type, AuditEvent.entity_id)


class IdempotencyKey(TenantScoped, Base):
    """Stored outcome of a mutating request, replayed when the same ``Idempotency-Key`` is retried."""

    __tablename__ = "idempotency_keys"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    principal_id: Mapped[str]
    method: Mapped[str]
    route: Mapped[str]
    key: Mapped[str]
    request_hash: Mapped[str]
    response_status: Mapped[int | None] = mapped_column(SmallInteger)
    response_body: Mapped[Any | None] = mapped_column(JSONB)
    response_headers: Mapped[dict[str, str] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]


Index(
    "uq_idempotency_keys_scope",
    IdempotencyKey.tenant_id,
    IdempotencyKey.principal_id,
    IdempotencyKey.method,
    IdempotencyKey.route,
    IdempotencyKey.key,
    unique=True,
)
Index("ix_idempotency_keys_expires_at", IdempotencyKey.expires_at)
