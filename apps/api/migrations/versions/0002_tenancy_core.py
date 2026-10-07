"""Tenancy and platform core: currencies, tenants, memberships, branches, numbering, audit, idempotency.

DDL is frozen here (not generated at run time) so later model changes cannot rewrite history. RLS, grants and
seed data follow ADR-0003; the catalog guard test checks the result.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import append_only, disable_tenant_rls, enable_tenant_rls, read_only

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CREATE_STATEMENTS = [
    """
    CREATE TABLE app.currencies (
        code CHAR(3) NOT NULL,
        name VARCHAR NOT NULL,
        minor_unit SMALLINT NOT NULL,
        CONSTRAINT pk_currencies PRIMARY KEY (code)
    )
    """,
    """
    CREATE TABLE app.tenants (
        id UUID NOT NULL,
        auth_org_id VARCHAR NOT NULL,
        slug VARCHAR,
        status VARCHAR DEFAULT 'active' NOT NULL,
        name VARCHAR NOT NULL,
        legal_name VARCHAR,
        registration_number VARCHAR,
        tax_pin VARCHAR,
        intermediary_type VARCHAR DEFAULT 'agent' NOT NULL,
        licence_number VARCHAR,
        licence_expiry DATE,
        email CITEXT,
        phone VARCHAR,
        address JSONB DEFAULT '{}'::jsonb NOT NULL,
        country_code CHAR(2) DEFAULT 'KE' NOT NULL,
        default_currency CHAR(3) DEFAULT 'KES' NOT NULL,
        timezone VARCHAR DEFAULT 'Africa/Nairobi' NOT NULL,
        locale VARCHAR DEFAULT 'en-KE' NOT NULL,
        fiscal_year_start_month SMALLINT DEFAULT '1' NOT NULL,
        quiet_hours_start TIME WITHOUT TIME ZONE DEFAULT '20:00',
        quiet_hours_end TIME WITHOUT TIME ZONE DEFAULT '07:00',
        provisioned_via VARCHAR DEFAULT 'hook' NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        created_by VARCHAR,
        updated_by VARCHAR,
        version INTEGER DEFAULT 1 NOT NULL,
        CONSTRAINT pk_tenants PRIMARY KEY (id),
        CONSTRAINT uq_tenants_auth_org_id UNIQUE (auth_org_id),
        CONSTRAINT fk_tenants_default_currency_currencies FOREIGN KEY(default_currency) REFERENCES app.currencies (code)
    )
    """,
    """
    CREATE TABLE app.audit_events (
        tenant_id UUID NOT NULL,
        occurred_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        actor_type VARCHAR NOT NULL,
        actor_id VARCHAR,
        action VARCHAR NOT NULL,
        entity_type VARCHAR NOT NULL,
        entity_id VARCHAR,
        request_id VARCHAR,
        changes JSONB DEFAULT '{}' NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        CONSTRAINT pk_audit_events PRIMARY KEY (id),
        CONSTRAINT uq_audit_events_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_audit_events_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES app.tenants (id)
    )
    """,
    """
    CREATE INDEX ix_audit_events_entity ON app.audit_events (tenant_id, entity_type, entity_id)
    """,
    """
    CREATE TABLE app.branches (
        name VARCHAR NOT NULL,
        code VARCHAR NOT NULL,
        tax_branch_id VARCHAR,
        email CITEXT,
        phone VARCHAR,
        address JSONB DEFAULT '{}'::jsonb NOT NULL,
        is_head_office BOOLEAN DEFAULT false NOT NULL,
        archived_at TIMESTAMP WITH TIME ZONE,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        created_by VARCHAR,
        updated_by VARCHAR,
        version INTEGER DEFAULT 1 NOT NULL,
        CONSTRAINT pk_branches PRIMARY KEY (id),
        CONSTRAINT uq_branches_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT uq_branches_tenant_id_code UNIQUE (tenant_id, code),
        CONSTRAINT fk_branches_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES app.tenants (id)
    )
    """,
    """
    CREATE TABLE app.idempotency_keys (
        tenant_id UUID NOT NULL,
        principal_id VARCHAR NOT NULL,
        method VARCHAR NOT NULL,
        route VARCHAR NOT NULL,
        key VARCHAR NOT NULL,
        request_hash VARCHAR NOT NULL,
        response_status SMALLINT,
        response_body JSONB,
        response_headers JSONB,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        CONSTRAINT pk_idempotency_keys PRIMARY KEY (id),
        CONSTRAINT uq_idempotency_keys_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_idempotency_keys_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES app.tenants (id)
    )
    """,
    """
    CREATE INDEX ix_idempotency_keys_expires_at ON app.idempotency_keys (expires_at)
    """,
    """
    CREATE UNIQUE INDEX uq_idempotency_keys_scope ON app.idempotency_keys (tenant_id, principal_id, method, route, key)
    """,
    """
    CREATE TABLE app.memberships (
        tenant_id UUID NOT NULL,
        auth_user_id VARCHAR NOT NULL,
        email CITEXT NOT NULL,
        name VARCHAR DEFAULT '' NOT NULL,
        role VARCHAR NOT NULL,
        status VARCHAR DEFAULT 'active' NOT NULL,
        phone VARCHAR,
        job_title VARCHAR,
        removed_at TIMESTAMP WITH TIME ZONE,
        id UUID DEFAULT uuidv7() NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        created_by VARCHAR,
        updated_by VARCHAR,
        version INTEGER DEFAULT 1 NOT NULL,
        CONSTRAINT pk_memberships PRIMARY KEY (id),
        CONSTRAINT uq_memberships_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT uq_memberships_tenant_id_auth_user_id UNIQUE (tenant_id, auth_user_id),
        CONSTRAINT fk_memberships_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES app.tenants (id)
    )
    """,
    """
    CREATE TABLE app.numbering_schemes (
        document_type VARCHAR NOT NULL,
        branch_id UUID,
        pattern VARCHAR NOT NULL,
        reset_period VARCHAR DEFAULT 'yearly' NOT NULL,
        start_at BIGINT DEFAULT 1 NOT NULL,
        is_active BOOLEAN DEFAULT true NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        created_by VARCHAR,
        updated_by VARCHAR,
        version INTEGER DEFAULT 1 NOT NULL,
        CONSTRAINT pk_numbering_schemes PRIMARY KEY (id),
        CONSTRAINT uq_numbering_schemes_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_numbering_schemes_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES app.tenants (id),
        CONSTRAINT fk_numbering_schemes_tenant_id_branch_id_branches FOREIGN KEY(tenant_id, branch_id) REFERENCES app.branches (tenant_id, id)
    )
    """,
    """
    CREATE UNIQUE INDEX uq_numbering_schemes_scope ON app.numbering_schemes (tenant_id, document_type, branch_id) NULLS NOT DISTINCT
    """,
    """
    CREATE TABLE app.number_sequences (
        tenant_id UUID NOT NULL,
        scheme_id UUID NOT NULL,
        period_key VARCHAR NOT NULL,
        last_value BIGINT NOT NULL,
        CONSTRAINT pk_number_sequences PRIMARY KEY (tenant_id, scheme_id, period_key),
        CONSTRAINT fk_number_sequences_tenant_id_scheme_id_numbering_schemes FOREIGN KEY(tenant_id, scheme_id) REFERENCES app.numbering_schemes (tenant_id, id)
    )
    """,
]

# Created in dependency order; dropped in reverse.
TABLES = [
    "currencies",
    "tenants",
    "audit_events",
    "branches",
    "idempotency_keys",
    "memberships",
    "numbering_schemes",
    "number_sequences",
]
TENANT_TABLES = {t: ("id" if t == "tenants" else "tenant_id") for t in TABLES if t != "currencies"}

CURRENCIES = [
    ("KES", "Kenyan shilling", 2),
    ("UGX", "Ugandan shilling", 0),
    ("TZS", "Tanzanian shilling", 2),
    ("RWF", "Rwandan franc", 0),
    ("BIF", "Burundian franc", 0),
    ("ETB", "Ethiopian birr", 2),
    ("SSP", "South Sudanese pound", 2),
    ("NGN", "Nigerian naira", 2),
    ("GHS", "Ghanaian cedi", 2),
    ("ZAR", "South African rand", 2),
    ("USD", "US dollar", 2),
    ("EUR", "Euro", 2),
    ("GBP", "Pound sterling", 2),
    ("AED", "UAE dirham", 2),
    ("INR", "Indian rupee", 2),
    ("JPY", "Japanese yen", 0),
    ("BHD", "Bahraini dinar", 3),
    ("KWD", "Kuwaiti dinar", 3),
]


def upgrade() -> None:
    for statement in CREATE_STATEMENTS:
        op.execute(statement)

    for table, column in TENANT_TABLES.items():
        for statement in enable_tenant_rls(table, column=column):
            op.execute(statement)

    # Expired idempotency keys of all tenants are purged by a periodic job (ADR-0011). app_user cannot see
    # other tenants' rows, so the purge runs in a SECURITY DEFINER function owned by app_owner (which never
    # serves requests) under a policy that only matches expired rows.
    op.execute(
        "CREATE POLICY purge_expired ON app.idempotency_keys FOR ALL TO app_owner "
        "USING (expires_at < now())"
    )
    op.execute(
        """
        CREATE FUNCTION app.purge_expired_idempotency_keys() RETURNS bigint
        LANGUAGE sql SECURITY DEFINER SET search_path = app, pg_temp AS $$
            WITH deleted AS (
                DELETE FROM app.idempotency_keys WHERE expires_at < now() RETURNING 1
            )
            SELECT count(*) FROM deleted
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION app.purge_expired_idempotency_keys() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app.purge_expired_idempotency_keys() TO app_user")

    for statement in [
        *read_only("currencies"),
        *append_only("audit_events"),
        # Tenant data is archived, never hard-deleted (CLAUDE.md rule 3).
        "REVOKE DELETE, TRUNCATE ON app.tenants, app.memberships, app.branches, "
        "app.numbering_schemes, app.number_sequences FROM app_user",
        "REVOKE TRUNCATE ON app.idempotency_keys FROM app_user",
    ]:
        op.execute(statement)

    currencies = sa.table(
        "currencies",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("minor_unit", sa.SmallInteger),
        schema="app",
    )
    op.bulk_insert(
        currencies,
        [{"code": code, "name": name, "minor_unit": minor} for code, name, minor in CURRENCIES],
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app.purge_expired_idempotency_keys()")
    op.execute("DROP POLICY IF EXISTS purge_expired ON app.idempotency_keys")
    for table in TENANT_TABLES:
        for statement in disable_tenant_rls(table):
            op.execute(statement)
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS app.{table}")
