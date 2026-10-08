"""Procrastinate job runner (ADR-0004).

Jobs live in Postgres (schema ``jobs``), so enqueuing inside a business transaction is atomic with the change
that caused it: this is our transactional outbox. Workers share the API image and codebase.

Run a worker:   procrastinate --app=app.workers.app.app worker
Health check:   procrastinate --app=app.workers.app.app healthchecks
"""

import procrastinate

from app.core.config import get_settings
from app.core.logging import configure_logging

JOBS_SCHEMA = "jobs"
QUEUES = ("default", "pdf", "messaging", "webhooks", "imports", "tax")


def libpq_dsn(sqlalchemy_url: str) -> str:
    """Convert a SQLAlchemy ``postgresql+psycopg://`` URL to a plain libpq DSN."""
    return sqlalchemy_url.replace("postgresql+psycopg://", "postgresql://", 1)


def create_job_app() -> procrastinate.App:
    settings = get_settings()
    configure_logging(settings)
    connector = procrastinate.PsycopgConnector(
        conninfo=libpq_dsn(str(settings.database_url)),
        kwargs={"options": f"-c search_path={JOBS_SCHEMA}"},
        min_size=1,
        max_size=5,
    )
    return procrastinate.App(
        connector=connector,
        import_paths=[
            "app.workers.tasks",
            "app.modules.messaging.tasks",
            "app.modules.tasks.tasks",
            "app.modules.policies.tasks",
        ],
    )


# Procrastinate's CLI loads the app by import path; the connector only connects when opened.
app = create_job_app()
