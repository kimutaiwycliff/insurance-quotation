"""Integration tests against the real Compose services (run via `make test`).

They prove the platform guarantees later milestones build on: dependencies are reachable, the API's
database role is least-privilege, and jobs can be enqueued by the API role (transactional outbox).
"""

import httpx
import psycopg
import pytest

from app.core.config import Settings
from app.workers.app import libpq_dsn


@pytest.fixture
def settings() -> Settings:
    return Settings()


async def test_ready_when_all_dependencies_are_up(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/ready")
    assert response.status_code == 200, response.text
    assert response.json()["checks"] == {"database": "ok", "valkey": "ok", "storage": "ok"}


async def test_api_role_is_least_privilege(settings: Settings) -> None:
    async with await psycopg.AsyncConnection.connect(libpq_dsn(str(settings.database_url))) as conn:
        row = await (
            await conn.execute(
                "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole "
                "FROM pg_roles WHERE rolname = current_user"
            )
        ).fetchone()
        assert row == (False, False, False, False)

        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await conn.execute("CREATE TABLE app.should_not_exist (id int)")


async def test_api_role_can_enqueue_jobs_in_a_transaction(settings: Settings) -> None:
    """The API enqueues jobs in the same transaction as the business change (ADR-0004)."""
    conn = await psycopg.AsyncConnection.connect(libpq_dsn(str(settings.database_url)))
    async with conn, conn.transaction(force_rollback=True):
        await conn.execute(
            "SELECT procrastinate_defer_jobs_v1(ARRAY[ROW("
            "'default', 'platform.heartbeat', 0, NULL, NULL, '{\"timestamp\": 0}'::jsonb, NOW()"
            ")::procrastinate_job_to_defer_v1])"
        )
        row = await (
            await conn.execute(
                "SELECT count(*) FROM procrastinate_jobs WHERE task_name = 'platform.heartbeat'"
            )
        ).fetchone()
        assert row is not None
        assert row[0] >= 1
