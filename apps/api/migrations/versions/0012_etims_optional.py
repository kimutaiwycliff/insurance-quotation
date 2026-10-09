"""R2.4: optional eTIMS: a tenant switch and the KRA control-unit details recorded on issued documents.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-09
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = {
    "etims_cu_invoice_number": "VARCHAR",
    "etims_verification_url": "VARCHAR",
    "etims_recorded_at": "TIMESTAMP WITH TIME ZONE",
    "etims_recorded_by": "VARCHAR",
}


def upgrade() -> None:
    op.execute("ALTER TABLE app.tenants ADD COLUMN etims_enabled BOOLEAN DEFAULT false NOT NULL")
    for name, kind in COLUMNS.items():
        op.execute(f"ALTER TABLE app.billing_documents ADD COLUMN {name} {kind}")
    # The eTIMS columns are recorded after issue, so the immutability trigger (ADR-0009) leaves them out on
    # purpose; one CU number belongs to one document.
    op.execute(
        "CREATE UNIQUE INDEX uq_billing_documents_etims ON app.billing_documents "
        "(tenant_id, etims_cu_invoice_number)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS app.uq_billing_documents_etims")
    for name in COLUMNS:
        op.execute(f"ALTER TABLE app.billing_documents DROP COLUMN IF EXISTS {name}")
    op.execute("ALTER TABLE app.tenants DROP COLUMN IF EXISTS etims_enabled")
