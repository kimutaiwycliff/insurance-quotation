"""Documents (files) with versions and links to any entity (client, policy, quote...)."""

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, ForeignKeyConstraint, Index, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Audited, Base, TenantScoped, Versioned


class Document(TenantScoped, Audited, Versioned, Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        # Generated documents (PDFs) are cached by a deterministic key, e.g. "render:<hash>".
        Index("uq_documents_source_key", "tenant_id", "source_key", unique=True),
        Index("ix_documents_expires_on", "tenant_id", "expires_on"),
    )

    category: Mapped[str]
    title: Mapped[str]
    status: Mapped[str] = mapped_column(server_default="active")  # active | archived
    current_version_no: Mapped[int | None]  # latest *ready* version
    expires_on: Mapped[date | None]  # e.g. ID or licence expiry (KYC reminders)
    source_key: Mapped[str | None]


class DocumentVersion(TenantScoped, Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "document_id", "version_no"),
        ForeignKeyConstraint(["tenant_id", "document_id"], ["documents.tenant_id", "documents.id"]),
    )

    document_id: Mapped[uuid.UUID]
    version_no: Mapped[int]
    storage_key: Mapped[str]
    filename: Mapped[str]
    content_type: Mapped[str]
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str | None]
    status: Mapped[str] = mapped_column(server_default="pending")  # pending | ready
    created_by: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finalized_at: Mapped[datetime | None]


class DocumentLink(TenantScoped, Base):
    __tablename__ = "document_links"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "document_id", "entity_type", "entity_id"),
        ForeignKeyConstraint(["tenant_id", "document_id"], ["documents.tenant_id", "documents.id"]),
        Index("ix_document_links_entity", "tenant_id", "entity_type", "entity_id"),
    )

    document_id: Mapped[uuid.UUID]
    entity_type: Mapped[str]
    entity_id: Mapped[uuid.UUID]
    created_by: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
