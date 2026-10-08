"""R1.5: commission received from insurers (allocated to policies), spreadsheet imports of the book.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-08
"""

from collections.abc import Sequence

from alembic import op

from app.core.rls import append_only, disable_tenant_rls, enable_tenant_rls

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CREATE_STATEMENTS = [
    """
    CREATE TABLE app.commission_receipts (
        insurer_name VARCHAR NOT NULL,
        received_on DATE NOT NULL,
        currency CHAR(3) NOT NULL,
        gross NUMERIC(20, 4) NOT NULL,
        wht NUMERIC(20, 4) NOT NULL,
        vat NUMERIC(20, 4) NOT NULL,
        net NUMERIC(20, 4) NOT NULL,
        reference VARCHAR,
        wht_certificate VARCHAR,
        notes VARCHAR,
        voided_at TIMESTAMP WITH TIME ZONE,
        void_reason VARCHAR,
        voided_by VARCHAR,
        created_by VARCHAR,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        CONSTRAINT pk_commission_receipts PRIMARY KEY (id),
        CONSTRAINT uq_commission_receipts_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT ck_commission_receipts_net CHECK (net >= 0)
    )
    """,
    "CREATE INDEX ix_commission_receipts_received ON app.commission_receipts (tenant_id, received_on)",
    """
    CREATE TABLE app.commission_allocations (
        receipt_id UUID NOT NULL,
        policy_id UUID NOT NULL,
        gross NUMERIC(20, 4) NOT NULL,
        wht NUMERIC(20, 4) NOT NULL,
        vat NUMERIC(20, 4) NOT NULL,
        net NUMERIC(20, 4) NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        CONSTRAINT pk_commission_allocations PRIMARY KEY (id),
        CONSTRAINT uq_commission_allocations_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT uq_commission_allocations_tenant_id_receipt_id_policy_id UNIQUE (tenant_id, receipt_id, policy_id),
        CONSTRAINT fk_commission_allocations_tenant_id_receipt_id_commissi_64df FOREIGN KEY(tenant_id, receipt_id) REFERENCES app.commission_receipts (tenant_id, id),
        CONSTRAINT fk_commission_allocations_tenant_id_policy_id_policies FOREIGN KEY(tenant_id, policy_id) REFERENCES app.policies (tenant_id, id)
    )
    """,
    "CREATE INDEX ix_commission_allocations_policy ON app.commission_allocations (tenant_id, policy_id)",
    """
    CREATE TABLE app.book_imports (
        filename VARCHAR NOT NULL,
        rows INTEGER NOT NULL,
        clients_created INTEGER NOT NULL,
        clients_matched INTEGER NOT NULL,
        policies_created INTEGER NOT NULL,
        rows_skipped INTEGER NOT NULL,
        options JSONB DEFAULT '{}'::jsonb NOT NULL,
        created_by VARCHAR,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        CONSTRAINT pk_book_imports PRIMARY KEY (id),
        CONSTRAINT uq_book_imports_tenant_id_id UNIQUE (tenant_id, id)
    )
    """,
]

TABLES = ["commission_receipts", "commission_allocations", "book_imports"]


def upgrade() -> None:
    for statement in CREATE_STATEMENTS:
        op.execute(statement)
    for table in TABLES:
        for statement in enable_tenant_rls(table):
            op.execute(statement)
    # Receipts are financial records: voided (the only update), never deleted. Allocations and the import log
    # are append-only.
    op.execute("REVOKE DELETE, TRUNCATE ON app.commission_receipts FROM app_user")
    for table in ("commission_allocations", "book_imports"):
        for statement in append_only(table):
            op.execute(statement)


def downgrade() -> None:
    for table in TABLES:
        for statement in disable_tenant_rls(table):
            op.execute(statement)
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS app.{table}")
