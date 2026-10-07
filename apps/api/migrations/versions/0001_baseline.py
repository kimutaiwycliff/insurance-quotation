"""Baseline: default privileges for app_user and the Procrastinate job schema.

Roles, schemas and extensions are created by the Postgres init script (infra/postgres/init) because they need
superuser rights; everything else lives in migrations.

Revision ID: 0001
Revises:
Create Date: 2026-10-07
"""

from collections.abc import Sequence

from alembic import op
from procrastinate.schema import SchemaManager

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Tables created by app_owner in schema "app" are usable (DML only) by app_user. RLS policies, added per
    # table from M1, then restrict which rows app_user can see.
    op.execute(
        "ALTER DEFAULT PRIVILEGES FOR ROLE app_owner IN SCHEMA app "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES FOR ROLE app_owner IN SCHEMA app "
        "GRANT USAGE, SELECT ON SEQUENCES TO app_user"
    )

    # Procrastinate job queue in its own schema. The SQL is pinned to the installed Procrastinate version;
    # upgrading Procrastinate requires a new revision applying its migration scripts (see ADR-0004).
    op.execute("CREATE SCHEMA IF NOT EXISTS jobs AUTHORIZATION app_owner")
    op.execute("SET LOCAL search_path TO jobs")
    op.execute(SchemaManager.get_schema())
    op.execute("SET LOCAL search_path TO app, public")
    op.execute("GRANT USAGE ON SCHEMA jobs TO app_user")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA jobs TO app_user")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA jobs TO app_user")
    op.execute("GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA jobs TO app_user")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS jobs CASCADE")
    op.execute(
        "ALTER DEFAULT PRIVILEGES FOR ROLE app_owner IN SCHEMA app "
        "REVOKE USAGE, SELECT ON SEQUENCES FROM app_user"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES FOR ROLE app_owner IN SCHEMA app "
        "REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM app_user"
    )
