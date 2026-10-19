"""Document designs: per-tenant design options (logo size and position, sections, paper).

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing RLS on app.branding_settings covers the new column.
    op.execute(
        "ALTER TABLE app.branding_settings ADD COLUMN options JSONB DEFAULT '{}'::jsonb NOT NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE app.branding_settings DROP COLUMN options")
