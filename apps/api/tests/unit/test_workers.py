"""Unit tests for the job runner wiring."""

from app.workers.app import QUEUES, app, libpq_dsn
from app.workers.tasks import heartbeat


def test_libpq_dsn_strips_sqlalchemy_driver() -> None:
    assert libpq_dsn("postgresql+psycopg://u:p@db:5432/app") == "postgresql://u:p@db:5432/app"


def test_heartbeat_is_registered_as_periodic_task() -> None:
    assert "platform.heartbeat" in app.tasks
    assert heartbeat.queue in QUEUES


async def test_heartbeat_runs() -> None:
    await heartbeat.func(timestamp=0)
