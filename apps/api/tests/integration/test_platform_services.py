"""Rate limiting, transactional job enqueue / events, idempotency-key purge."""

import uuid
from collections.abc import AsyncIterator, Callable

import httpx
import psycopg
from sqlalchemy import text

from app.core import db
from app.core.config import Settings
from app.core.tenancy import tenant_id_for_org
from app.platform import events
from app.platform.idempotency import purge_expired
from app.workers.app import libpq_dsn
from tests.support import Org


async def test_rate_limit_returns_429_with_retry_after(
    make_api: Callable[..., AsyncIterator[httpx.AsyncClient]], org: Org
) -> None:
    async for api in make_api(rate_limit_read_per_minute=3):
        responses = [await api.get("/api/v1/me", headers=org.headers()) for _ in range(8)]
        statuses = [r.status_code for r in responses]
        # Fixed one-minute windows: even a run straddling a window boundary passes at most 2 x 3 requests.
        assert statuses[0] == 200
        assert statuses.count(200) <= 6
        response = next(r for r in responses if r.status_code == 429)
        assert response.json()["code"] == "rate_limited"
        assert 1 <= int(response.headers["Retry-After"]) <= 60


async def _job_count(settings: Settings, event_id_marker: str) -> int:
    async with await psycopg.AsyncConnection.connect(libpq_dsn(str(settings.database_url))) as conn:
        row = await (
            await conn.execute(
                "SELECT count(*) FROM jobs.procrastinate_jobs WHERE args->'payload'->>'marker' = %s",
                (event_id_marker,),
            )
        ).fetchone()
        assert row is not None
        return int(row[0])


async def test_events_are_enqueued_with_the_transaction(settings: Settings, ready_org: Org) -> None:
    events.subscribe("test.happened", "platform.heartbeat")
    tenant_id = tenant_id_for_org(ready_org.org_id)
    engine = db.create_engine(settings)
    factory = db.create_session_factory(engine)
    committed, rolled_back = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        async with db.tenant_scope(factory, tenant_id) as session:
            job_ids = await events.publish(
                session, "test.happened", tenant_id, {"marker": committed}
            )
            assert len(job_ids) == 1
        try:
            async with db.tenant_scope(factory, tenant_id) as session:
                await events.publish(session, "test.happened", tenant_id, {"marker": rolled_back})
                raise RuntimeError("business change failed")
        except RuntimeError:
            pass
    finally:
        await engine.dispose()
    assert await _job_count(settings, committed) == 1
    assert await _job_count(settings, rolled_back) == 0  # the outbox rolled back with the change
    assert events.subscribers("nobody.listens") == []


async def test_purge_removes_only_expired_keys(
    settings: Settings, api: httpx.AsyncClient, ready_org: Org, owner_conn: psycopg.AsyncConnection
) -> None:
    headers = ready_org.headers()
    for code, key in (("EXP", "expired-key-1"), ("LIV", "live-key-0001")):
        await api.post(
            "/api/v1/branches",
            json={"name": code, "code": code},
            headers=headers | {"Idempotency-Key": key},
        )
    tenant_id = tenant_id_for_org(ready_org.org_id)
    await owner_conn.execute("SELECT set_config('app.tenant_id', %s, false)", (str(tenant_id),))
    await owner_conn.execute(
        "UPDATE app.idempotency_keys SET expires_at = now() - interval '1 hour' WHERE key = 'expired-key-1'"
    )
    engine = db.create_engine(settings)
    try:
        async with db.session_scope(db.create_session_factory(engine)) as session:
            assert await purge_expired(session) >= 1
        async with db.tenant_scope(db.create_session_factory(engine), tenant_id) as session:
            keys = set(
                (await session.execute(text("SELECT key FROM app.idempotency_keys"))).scalars()
            )
    finally:
        await engine.dispose()
    assert keys == {"live-key-0001"}
