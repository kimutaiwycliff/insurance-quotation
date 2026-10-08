"""Tasks and follow-ups, optionally linked to a record (client, lead, later policies and quotes)."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Audited, Base, TenantScoped, Versioned


class Task(TenantScoped, Audited, Versioned, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        Index("ix_tasks_assignee_due", "tenant_id", "assignee_user_id", "status", "due_at"),
        Index("ix_tasks_entity", "tenant_id", "entity_type", "entity_id"),
        Index(
            "ix_tasks_due_unreminded",
            "due_at",
            postgresql_where="status = 'open' AND reminded_at IS NULL",
        ),
    )

    title: Mapped[str]
    notes: Mapped[str | None]
    due_at: Mapped[datetime | None]
    assignee_user_id: Mapped[str]
    priority: Mapped[str] = mapped_column(server_default="normal")  # low | normal | high
    status: Mapped[str] = mapped_column(server_default="open")  # open | done
    completed_at: Mapped[datetime | None]
    entity_type: Mapped[str | None]
    entity_id: Mapped[uuid.UUID | None]
    reminded_at: Mapped[datetime | None]
