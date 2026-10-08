"""Clients (individual and corporate), households, corporate contacts and the activity log."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import ForeignKeyConstraint, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Audited, Base, TenantScoped, Versioned


class Household(TenantScoped, Audited, Versioned, Base):
    """A family or group whose policies are managed together (e.g. one client's spouse and children)."""

    __tablename__ = "households"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )

    name: Mapped[str]
    notes: Mapped[str | None]


class Client(TenantScoped, Audited, Versioned, Base):
    __tablename__ = "clients"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        ForeignKeyConstraint(
            ["tenant_id", "household_id"], ["households.tenant_id", "households.id"]
        ),
        ForeignKeyConstraint(["tenant_id", "referred_by_id"], ["clients.tenant_id", "clients.id"]),
        Index("ix_clients_owner", "tenant_id", "owner_user_id"),
        Index("ix_clients_phone", "tenant_id", "phone"),
        Index("ix_clients_email", "tenant_id", "email"),
        Index("ix_clients_kra_pin", "tenant_id", "kra_pin"),
        Index("ix_clients_id_number_hash", "tenant_id", "id_number_hash"),
        Index(
            "ix_clients_display_name_trgm",
            "display_name",
            postgresql_using="gin",
            postgresql_ops={"display_name": "gin_trgm_ops"},
        ),
    )

    kind: Mapped[str]  # individual | corporate
    display_name: Mapped[str]
    first_name: Mapped[str | None]
    last_name: Mapped[str | None]
    other_names: Mapped[str | None]
    company_name: Mapped[str | None]
    email: Mapped[str | None] = mapped_column(CITEXT)
    phone: Mapped[str | None]  # E.164
    alt_phone: Mapped[str | None]
    preferred_channel: Mapped[str] = mapped_column(
        server_default="whatsapp"
    )  # whatsapp|sms|email|call
    kra_pin: Mapped[str | None]
    id_type: Mapped[str | None]  # national_id | passport | alien_id | business_registration
    id_number_enc: Mapped[str | None]  # AES-GCM (ADR-0018)
    id_number_hash: Mapped[str | None]  # HMAC for exact lookup
    id_number_hint: Mapped[str | None]  # last 3 characters, masked
    date_of_birth: Mapped[date | None]
    gender: Mapped[str | None]
    occupation: Mapped[str | None]
    address: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    source: Mapped[str | None]  # walk_in | referral | lead | social | website | other
    referred_by_id: Mapped[uuid.UUID | None]
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), server_default=text("'{}'"))
    owner_user_id: Mapped[str | None]  # the agent responsible for this client
    household_id: Mapped[uuid.UUID | None]
    household_role: Mapped[str | None]  # head | spouse | child | parent | other
    marketing_consent: Mapped[bool] = mapped_column(server_default=text("false"))
    marketing_consent_at: Mapped[datetime | None]
    notes: Mapped[str | None]
    status: Mapped[str] = mapped_column(server_default="active")  # active | archived
    archived_at: Mapped[datetime | None]


class ClientContact(TenantScoped, Audited, Base):
    """People at a corporate client (finance, HR, decision maker)."""

    __tablename__ = "client_contacts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(["tenant_id", "client_id"], ["clients.tenant_id", "clients.id"]),
        Index("ix_client_contacts_client", "tenant_id", "client_id"),
    )

    client_id: Mapped[uuid.UUID]
    name: Mapped[str]
    role: Mapped[str | None]
    email: Mapped[str | None] = mapped_column(CITEXT)
    phone: Mapped[str | None]
    is_primary: Mapped[bool] = mapped_column(server_default=text("false"))


class Activity(TenantScoped, Base):
    """What happened with a client: notes, calls, meetings, messages (append-only log for the 360° view)."""

    __tablename__ = "client_activities"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(["tenant_id", "client_id"], ["clients.tenant_id", "clients.id"]),
        Index("ix_client_activities_client", "tenant_id", "client_id", "occurred_at"),
    )

    client_id: Mapped[uuid.UUID]
    kind: Mapped[str]  # note | call | meeting | whatsapp | sms | email | visit
    body: Mapped[str]
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now())
    created_by: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
