"""Task reminder jobs."""

import uuid

from app.core import db
from app.core.config import get_settings
from app.modules.tasks import service
from app.workers.app import app


@app.periodic(cron="*/5 * * * *", periodic_id="enqueue_task_reminders")
@app.task(queue="default", name="tasks.enqueue_due_reminders")
async def enqueue_due_reminders(timestamp: int) -> None:
    engine = db.create_engine(get_settings())
    try:
        async with db.session_scope(db.create_session_factory(engine)) as session:
            await service.enqueue_due_reminders(session)
    finally:
        await engine.dispose()


@app.task(queue="default", name=service.REMIND_TASK, retry=3)
async def remind(tenant_id: str, task_id: str) -> None:
    settings = get_settings()
    engine = db.create_engine(settings)
    try:
        async with db.tenant_scope(
            db.create_session_factory(engine), uuid.UUID(tenant_id)
        ) as session:
            await service.remind(session, settings, uuid.UUID(tenant_id), uuid.UUID(task_id))
    finally:
        await engine.dispose()
