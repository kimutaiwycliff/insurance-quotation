"""In-app notifications (the bell) and per-user preferences."""

from datetime import datetime

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantScoped


class Notification(TenantScoped, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        Index("ix_notifications_recipient", "tenant_id", "user_id", "read_at"),
    )

    user_id: Mapped[str]  # auth user id of the recipient
    kind: Mapped[str]
    title: Mapped[str]
    body: Mapped[str] = mapped_column(server_default="")
    link: Mapped[str | None]  # app-relative path, e.g. /quotes/<id>
    read_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class NotificationPreference(TenantScoped, Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "user_id", "kind"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )

    user_id: Mapped[str]
    kind: Mapped[str]
    in_app: Mapped[bool] = mapped_column(server_default=text("true"))
    email: Mapped[bool] = mapped_column(server_default=text("false"))
