"""Leads: prospects in the agent's sales pipeline."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CHAR, ForeignKeyConstraint, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Audited, Base, MoneyColumn, TenantScoped, Versioned


class Lead(TenantScoped, Audited, Versioned, Base):
    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        ForeignKeyConstraint(["tenant_id", "client_id"], ["clients.tenant_id", "clients.id"]),
        Index("ix_leads_stage", "tenant_id", "stage", "owner_user_id"),
        Index("ix_leads_follow_up", "tenant_id", "next_follow_up_at"),
    )

    name: Mapped[str]
    phone: Mapped[str | None]
    email: Mapped[str | None] = mapped_column(CITEXT)
    source: Mapped[str] = mapped_column(server_default="other")
    interests: Mapped[list[str]] = mapped_column(ARRAY(String), server_default=text("'{}'"))
    stage: Mapped[str] = mapped_column(server_default="new")  # new|contacted|quoted|won|lost
    lost_reason: Mapped[str | None]
    estimated_premium: Mapped[Decimal | None] = mapped_column(MoneyColumn)
    currency: Mapped[str] = mapped_column(CHAR(3), server_default="KES")
    owner_user_id: Mapped[str]
    next_follow_up_at: Mapped[datetime | None]
    notes: Mapped[str | None]
    client_id: Mapped[uuid.UUID | None]  # set when converted (won) or linked to an existing client
    stage_changed_at: Mapped[datetime | None]
