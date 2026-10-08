"""Tenancy tables: tenants (organizations), memberships (users within a tenant) and branches."""

import uuid
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import CHAR, ForeignKey, ForeignKeyConstraint, SmallInteger, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Audited, Base, TenantScoped, Versioned


class Tenant(Audited, Versioned, Base):
    """One agency or business. RLS key is ``id`` (it *is* the tenant id)."""

    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    auth_org_id: Mapped[str] = mapped_column(unique=True)
    slug: Mapped[str | None]
    status: Mapped[str] = mapped_column(server_default="active")  # active | suspended
    name: Mapped[str]  # trading / display name
    legal_name: Mapped[str | None]
    registration_number: Mapped[str | None]
    tax_pin: Mapped[str | None]  # KRA PIN for Kenyan tenants
    # agent | broker | business: drives defaults such as withholding tax on commission (SPEC_REVIEW §2).
    intermediary_type: Mapped[str] = mapped_column(server_default="agent")
    licence_number: Mapped[str | None]  # IRA licence
    licence_expiry: Mapped[date | None]
    email: Mapped[str | None] = mapped_column(CITEXT)
    phone: Mapped[str | None]
    address: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    country_code: Mapped[str] = mapped_column(CHAR(2), server_default="KE")
    default_currency: Mapped[str] = mapped_column(
        CHAR(3), ForeignKey("currencies.code"), server_default="KES"
    )
    timezone: Mapped[str] = mapped_column(server_default="Africa/Nairobi")
    locale: Mapped[str] = mapped_column(server_default="en-KE")
    fiscal_year_start_month: Mapped[int] = mapped_column(SmallInteger, server_default="1")
    # Reminders are not sent between these local times.
    quiet_hours_start: Mapped[time | None] = mapped_column(server_default=text("'20:00'"))
    quiet_hours_end: Mapped[time | None] = mapped_column(server_default=text("'07:00'"))
    provisioned_via: Mapped[str] = mapped_column(server_default="hook")  # hook | lazy
    # Whether quotes may compare several insurers (pending legal opinion D5 for tied agents).
    multi_insurer_quotes: Mapped[bool] = mapped_column(server_default=text("true"))
    # Days before expiry on which the agent is reminded about a renewal (and, if enabled, the client emailed).
    renewal_reminder_days: Mapped[list[int]] = mapped_column(
        ARRAY(SmallInteger), server_default=text("'{30,14,7}'")
    )
    renewal_client_emails: Mapped[bool] = mapped_column(server_default=text("false"))
    # Invoice and quote reminders emailed to clients (R2.2); off until the tenant turns them on.
    billing_reminders: Mapped[bool] = mapped_column(server_default=text("false"))
    invoice_reminder_days_before: Mapped[list[int]] = mapped_column(
        ARRAY(SmallInteger), server_default=text("'{3}'")
    )
    invoice_reminder_days_after: Mapped[list[int]] = mapped_column(
        ARRAY(SmallInteger), server_default=text("'{1,7,14}'")
    )


class Membership(TenantScoped, Audited, Versioned, Base):
    """Mirror of a Better Auth organization member, plus the user's profile within this tenant."""

    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "auth_user_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    auth_user_id: Mapped[str]
    email: Mapped[str] = mapped_column(CITEXT)
    name: Mapped[str] = mapped_column(server_default="")
    role: Mapped[str]
    status: Mapped[str] = mapped_column(server_default="active")  # active | removed
    phone: Mapped[str | None]
    job_title: Mapped[str | None]
    removed_at: Mapped[datetime | None]


class Branch(TenantScoped, Audited, Versioned, Base):
    __tablename__ = "branches"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "code"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )

    name: Mapped[str]
    code: Mapped[str]  # short uppercase code, usable as {BRANCH} in numbering patterns
    tax_branch_id: Mapped[str | None]  # eTIMS branch id (bhfId) when the tenant is registered
    email: Mapped[str | None] = mapped_column(CITEXT)
    phone: Mapped[str | None]
    address: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    is_head_office: Mapped[bool] = mapped_column(server_default=text("false"))
    archived_at: Mapped[datetime | None]
