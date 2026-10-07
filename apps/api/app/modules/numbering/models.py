"""Numbering schemes and their gapless counters."""

import uuid

from sqlalchemy import (
    BigInteger,
    ForeignKeyConstraint,
    Index,
    PrimaryKeyConstraint,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Audited, Base, TenantScoped, Versioned


class NumberingScheme(TenantScoped, Audited, Versioned, Base):
    """How numbers of one document type (optionally per branch) are formatted and reset."""

    __tablename__ = "numbering_schemes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        ForeignKeyConstraint(["tenant_id", "branch_id"], ["branches.tenant_id", "branches.id"]),
        Index(
            "uq_numbering_schemes_scope",
            "tenant_id",
            "document_type",
            "branch_id",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
    )

    document_type: Mapped[str]
    branch_id: Mapped[uuid.UUID | None]
    pattern: Mapped[str]
    reset_period: Mapped[str] = mapped_column(server_default="yearly")
    start_at: Mapped[int] = mapped_column(BigInteger, server_default=text("1"))
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))


class NumberSequence(Base):
    """Last number issued per scheme and period. Incremented with a row lock inside the issuing transaction,
    so a rolled-back issue gives its number back (gapless)."""

    __tablename__ = "number_sequences"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "scheme_id", "period_key"),
        ForeignKeyConstraint(
            ["tenant_id", "scheme_id"], ["numbering_schemes.tenant_id", "numbering_schemes.id"]
        ),
    )

    tenant_id: Mapped[uuid.UUID]
    scheme_id: Mapped[uuid.UUID]
    period_key: Mapped[str]
    last_value: Mapped[int] = mapped_column(BigInteger)
