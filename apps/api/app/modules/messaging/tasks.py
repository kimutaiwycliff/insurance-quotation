"""Messaging jobs (registered on the Procrastinate app; the API enqueues them by name)."""

import uuid

from app.core import db
from app.core.config import get_settings
from app.modules.messaging import service
from app.workers.app import app


@app.task(queue="messaging", name=service.SEND_TASK, retry=3)
async def send_email(tenant_id: str, message_id: str) -> None:
    settings = get_settings()
    engine = db.create_engine(settings)
    try:
        async with db.tenant_scope(
            db.create_session_factory(engine), uuid.UUID(tenant_id)
        ) as session:
            await service.send_queued(
                session, service.sender_for(settings), settings, uuid.UUID(message_id)
            )
    finally:
        await engine.dispose()
