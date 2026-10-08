"""R1.2: insurers and products (rates, minimum premiums, benefits, commission rates).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-08
"""

from collections.abc import Sequence

from alembic import op

from app.core.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CREATE_STATEMENTS = [
    """
    CREATE TABLE app.insurers (
        name CITEXT NOT NULL,
        short_name VARCHAR,
        email CITEXT,
        phone VARCHAR,
        mpesa_paybill VARCHAR,
        payment_account_hint VARCHAR,
        bank_details JSONB DEFAULT '{}'::jsonb NOT NULL,
        notes VARCHAR,
        is_active BOOLEAN DEFAULT true NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        created_by VARCHAR,
        updated_by VARCHAR,
        version INTEGER DEFAULT 1 NOT NULL,
        CONSTRAINT pk_insurers PRIMARY KEY (id),
        CONSTRAINT uq_insurers_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_insurers_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES app.tenants (id)
    )
    """,
    """
    CREATE UNIQUE INDEX uq_insurers_name ON app.insurers (tenant_id, name)
    """,
    """
    CREATE TABLE app.products (
        insurer_id UUID NOT NULL,
        class_code VARCHAR NOT NULL,
        name VARCHAR NOT NULL,
        currency CHAR(3) DEFAULT 'KES' NOT NULL,
        rating_basis VARCHAR NOT NULL,
        rate NUMERIC(12, 8),
        flat_premium NUMERIC(20, 4),
        min_premium NUMERIC(20, 4) DEFAULT 0 NOT NULL,
        benefits JSONB DEFAULT '[]'::jsonb NOT NULL,
        member_tiers JSONB DEFAULT '[]'::jsonb NOT NULL,
        excess_text VARCHAR,
        commission_rate_new NUMERIC(12, 8),
        commission_rate_renewal NUMERIC(12, 8),
        notes VARCHAR,
        is_active BOOLEAN DEFAULT true NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        created_by VARCHAR,
        updated_by VARCHAR,
        version INTEGER DEFAULT 1 NOT NULL,
        CONSTRAINT pk_products PRIMARY KEY (id),
        CONSTRAINT uq_products_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_products_tenant_id_insurer_id_insurers FOREIGN KEY(tenant_id, insurer_id) REFERENCES app.insurers (tenant_id, id)
    )
    """,
    """
    CREATE INDEX ix_products_class ON app.products (tenant_id, class_code)
    """,
    """
    CREATE UNIQUE INDEX uq_products_name ON app.products (tenant_id, insurer_id, name)
    """,
]

TABLES = ["insurers", "products"]


def upgrade() -> None:
    for statement in CREATE_STATEMENTS:
        op.execute(statement)
    for table in TABLES:
        for statement in enable_tenant_rls(table):
            op.execute(statement)
    # Insurers and products are deactivated, never deleted: quotes and policies refer to them.
    op.execute("REVOKE DELETE, TRUNCATE ON app.insurers, app.products FROM app_user")


def downgrade() -> None:
    for table in TABLES:
        for statement in disable_tenant_rls(table):
            op.execute(statement)
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS app.{table}")
