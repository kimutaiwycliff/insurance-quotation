"""Renewal reminder jobs."""

import uuid

from app.core import db
from app.core.config import get_settings
from app.modules.policies import service
from app.workers.app import app


# 05:00 UTC = 08:00 in Nairobi; each agency's own date is used inside the scan.
@app.periodic(cron="0 5 * * *", periodic_id="enqueue_renewal_reminders")
@app.task(queue="default", name="policies.enqueue_renewal_reminders")
async def enqueue_renewal_reminders(timestamp: int) -> None:
    engine = db.create_engine(get_settings())
    try:
        async with db.session_scope(db.create_session_factory(engine)) as session:
            await service.enqueue_renewal_reminders(session)
    finally:
        await engine.dispose()


@app.task(queue="default", name=service.REMIND_RENEWAL, retry=3)
async def remind_renewal(tenant_id: str, policy_id: str, offset_days: int) -> None:
    settings = get_settings()
    engine = db.create_engine(settings)
    try:
        async with db.tenant_scope(
            db.create_session_factory(engine), uuid.UUID(tenant_id)
        ) as session:
            await service.send_renewal_reminder(
                session, settings, uuid.UUID(tenant_id), uuid.UUID(policy_id), offset_days
            )
    finally:
        await engine.dispose()
