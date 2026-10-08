"""M-Pesa jobs: act on stored callbacks, and check prompts whose callback is late."""

import uuid

import httpx

from app.core import db
from app.core.config import get_settings
from app.modules.mpesa import service
from app.workers.app import app


@app.task(queue="webhooks", name=service.PROCESS_EVENT, retry=5)
async def process_event(tenant_id: str, event_id: str) -> None:
    settings = get_settings()
    engine = db.create_engine(settings)
    try:
        async with (
            httpx.AsyncClient() as http,
            db.tenant_scope(db.create_session_factory(engine), uuid.UUID(tenant_id)) as session,
        ):
            await service.process_event(session, settings, http, uuid.UUID(event_id))
    finally:
        await engine.dispose()


@app.periodic(cron="* * * * *", periodic_id="mpesa_check_pending")
@app.task(queue="webhooks", name="mpesa.enqueue_checks")
async def enqueue_checks(timestamp: int) -> None:
    engine = db.create_engine(get_settings())
    try:
        async with db.session_scope(db.create_session_factory(engine)) as session:
            await service.enqueue_checks(session)
    finally:
        await engine.dispose()


@app.task(queue="webhooks", name=service.CHECK_REQUEST, retry=2)
async def check_request(tenant_id: str, request_id: str) -> None:
    settings = get_settings()
    engine = db.create_engine(settings)
    try:
        async with (
            httpx.AsyncClient() as http,
            db.tenant_scope(db.create_session_factory(engine), uuid.UUID(tenant_id)) as session,
        ):
            await service.check_request(
                session, settings, http, uuid.UUID(tenant_id), uuid.UUID(request_id)
            )
    finally:
        await engine.dispose()
