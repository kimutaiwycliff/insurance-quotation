"""Invoice and quote reminder jobs."""

import uuid

from app.core import db
from app.core.config import get_settings
from app.modules.billing import service
from app.workers.app import app


# 05:30 UTC = 08:30 in Nairobi (after renewal reminders); each tenant's own date is used in the scan.
@app.periodic(cron="30 5 * * *", periodic_id="enqueue_billing_reminders")
@app.task(queue="default", name="billing.enqueue_reminders")
async def enqueue_billing_reminders(timestamp: int) -> None:
    engine = db.create_engine(get_settings())
    try:
        async with db.session_scope(db.create_session_factory(engine)) as session:
            await service.enqueue_billing_reminders(session)
    finally:
        await engine.dispose()


@app.task(queue="messaging", name=service.REMIND_BILLING, retry=3)
async def remind(tenant_id: str, document_id: str, kind: str, offset_days: int) -> None:
    settings = get_settings()
    engine = db.create_engine(settings)
    try:
        async with db.tenant_scope(
            db.create_session_factory(engine), uuid.UUID(tenant_id)
        ) as session:
            await service.send_billing_reminder(
                session,
                settings,
                uuid.UUID(tenant_id),
                document_id=uuid.UUID(document_id),
                kind=kind,
                offset_days=offset_days,
            )
    finally:
        await engine.dispose()
