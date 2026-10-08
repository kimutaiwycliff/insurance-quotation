"""R1.3: insurance quotes with frozen insurer options; per-agency multi-insurer switch (D5).

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-08
"""

from collections.abc import Sequence

from alembic import op

from app.core.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CREATE_STATEMENTS = [
    """
    CREATE TABLE app.quotes (
        number VARCHAR,
        client_id UUID NOT NULL,
        owner_user_id VARCHAR NOT NULL,
        class_code VARCHAR NOT NULL,
        title VARCHAR NOT NULL,
        currency CHAR(3) DEFAULT 'KES' NOT NULL,
        status VARCHAR DEFAULT 'draft' NOT NULL,
        risk JSONB NOT NULL,
        details JSONB DEFAULT '[]'::jsonb NOT NULL,
        notes VARCHAR,
        valid_until DATE NOT NULL,
        sent_at TIMESTAMP WITH TIME ZONE,
        document_id UUID,
        accepted_position INTEGER,
        responded_at TIMESTAMP WITH TIME ZONE,
        response JSONB DEFAULT '{}'::jsonb NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        created_by VARCHAR,
        updated_by VARCHAR,
        version INTEGER DEFAULT 1 NOT NULL,
        CONSTRAINT pk_quotes PRIMARY KEY (id),
        CONSTRAINT uq_quotes_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_quotes_tenant_id_client_id_clients FOREIGN KEY(tenant_id, client_id) REFERENCES app.clients (tenant_id, id),
        CONSTRAINT fk_quotes_tenant_id_document_id_documents FOREIGN KEY(tenant_id, document_id) REFERENCES app.documents (tenant_id, id)
    )
    """,
    """
    CREATE INDEX ix_quotes_client ON app.quotes (tenant_id, client_id)
    """,
    """
    CREATE INDEX ix_quotes_owner_status ON app.quotes (tenant_id, owner_user_id, status)
    """,
    """
    CREATE UNIQUE INDEX uq_quotes_number ON app.quotes (tenant_id, number)
    """,
    """
    CREATE TABLE app.quote_options (
        quote_id UUID NOT NULL,
        position INTEGER NOT NULL,
        product_id UUID NOT NULL,
        insurer_name VARCHAR NOT NULL,
        product_name VARCHAR NOT NULL,
        excess_text VARCHAR,
        breakdown JSONB NOT NULL,
        client_total NUMERIC(20, 4) NOT NULL,
        commission JSONB,
        needs_input BOOLEAN DEFAULT false NOT NULL,
        recommended BOOLEAN DEFAULT false NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        CONSTRAINT pk_quote_options PRIMARY KEY (id),
        CONSTRAINT uq_quote_options_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT uq_quote_options_tenant_id_quote_id_position UNIQUE (tenant_id, quote_id, position),
        CONSTRAINT fk_quote_options_tenant_id_quote_id_quotes FOREIGN KEY(tenant_id, quote_id) REFERENCES app.quotes (tenant_id, id),
        CONSTRAINT fk_quote_options_tenant_id_product_id_products FOREIGN KEY(tenant_id, product_id) REFERENCES app.products (tenant_id, id)
    )
    """,
]

TABLES = ["quotes", "quote_options"]


def upgrade() -> None:
    op.execute(
        "ALTER TABLE app.tenants ADD COLUMN multi_insurer_quotes BOOLEAN DEFAULT true NOT NULL"
    )
    for statement in CREATE_STATEMENTS:
        op.execute(statement)
    for table in TABLES:
        for statement in enable_tenant_rls(table):
            op.execute(statement)
    # Quotes are withdrawn, never deleted. Options of *draft* quotes are replaced on recalculation.
    op.execute("REVOKE DELETE, TRUNCATE ON app.quotes FROM app_user")
    op.execute("REVOKE TRUNCATE ON app.quote_options FROM app_user")


def downgrade() -> None:
    for table in TABLES:
        for statement in disable_tenant_rls(table):
            op.execute(statement)
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS app.{table}")
    op.execute("ALTER TABLE app.tenants DROP COLUMN IF EXISTS multi_insurer_quotes")
