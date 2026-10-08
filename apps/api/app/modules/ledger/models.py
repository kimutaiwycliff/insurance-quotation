"""Double-entry journal (ADR-0012): append-only, balanced per entry and currency (deferred DB check)."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CHAR, CheckConstraint, ForeignKeyConstraint, Index, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, MoneyColumn, TenantScoped

ACCOUNTS = ("receivable", "cash", "client_credit", "tax_payable", "revenue")


class JournalEntry(TenantScoped, Base):
    __tablename__ = "journal_entries"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        Index("ix_journal_entries_source", "tenant_id", "source_type", "source_id"),
    )

    occurred_on: Mapped[date]
    source_type: Mapped[str]  # invoice | credit_note | payment | allocation ...
    source_id: Mapped[uuid.UUID]
    memo: Mapped[str]
    created_by: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class JournalLine(TenantScoped, Base):
    __tablename__ = "journal_lines"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "entry_id"], ["journal_entries.tenant_id", "journal_entries.id"]
        ),
        Index("ix_journal_lines_entry", "tenant_id", "entry_id"),
        Index("ix_journal_lines_account_client", "tenant_id", "account", "client_id"),
        CheckConstraint(
            "account IN ('receivable', 'cash', 'client_credit', 'tax_payable', 'revenue')",
            name="account",
        ),
        CheckConstraint(
            "debit >= 0 AND credit >= 0 AND (debit = 0) <> (credit = 0)", name="one_side"
        ),
    )

    entry_id: Mapped[uuid.UUID]
    account: Mapped[str]
    debit: Mapped[Decimal] = mapped_column(MoneyColumn)
    credit: Mapped[Decimal] = mapped_column(MoneyColumn)
    currency: Mapped[str] = mapped_column(CHAR(3))
    client_id: Mapped[uuid.UUID | None]
