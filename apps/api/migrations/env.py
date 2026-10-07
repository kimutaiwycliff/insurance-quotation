"""Alembic environment. Migrations always run as the schema owner (``app_owner``), never as ``app_user``."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_settings

APP_SCHEMA = "app"

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Feature modules register their tables on this metadata from M1 (see app/core/models.py then).
target_metadata = None


def _url() -> str:
    url = get_settings().migrations_database_url
    if url is None:
        raise RuntimeError("MIGRATIONS_DATABASE_URL must be set to run migrations")
    return str(url)


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        version_table_schema=APP_SCHEMA,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=APP_SCHEMA,
            include_schemas=True,
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
