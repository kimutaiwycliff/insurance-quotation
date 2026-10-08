"""A log of spreadsheet imports of the agent's existing book."""

from datetime import datetime
from typing import Any

from sqlalchemy import UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantScoped


class BookImport(TenantScoped, Base):
    __tablename__ = "book_imports"
    __table_args__ = (UniqueConstraint("tenant_id", "id"),)

    filename: Mapped[str]
    rows: Mapped[int]
    clients_created: Mapped[int]
    clients_matched: Mapped[int]
    policies_created: Mapped[int]
    rows_skipped: Mapped[int]
    options: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_by: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
