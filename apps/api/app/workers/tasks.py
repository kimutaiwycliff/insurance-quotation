"""Job definitions. Feature modules register their jobs in their own ``tasks.py``.

Rules (see CLAUDE.md): jobs take IDs (never ORM objects), re-fetch state, and are idempotent.
"""

import structlog

from app.core import db
from app.core.config import get_settings
from app.platform.idempotency import purge_expired
from app.workers.app import app

logger = structlog.get_logger(__name__)


@app.periodic(cron="*/5 * * * *", periodic_id="worker_heartbeat")
@app.task(queue="default", name="platform.heartbeat")
async def heartbeat(timestamp: int) -> None:
    """Proves the worker and scheduler are alive; alert if heartbeats stop."""
    logger.info("worker_heartbeat", scheduled_for=timestamp)


@app.periodic(cron="17 * * * *", periodic_id="purge_idempotency_keys")
@app.task(queue="default", name="platform.purge_idempotency_keys")
async def purge_idempotency_keys(timestamp: int) -> None:
    """Delete expired idempotency keys of all tenants (policy ``purge_expired``, ADR-0011)."""
    engine = db.create_engine(get_settings())
    try:
        async with db.session_scope(db.create_session_factory(engine)) as session:
            deleted = await purge_expired(session)
        logger.info("idempotency_keys_purged", deleted=deleted, scheduled_for=timestamp)
    finally:
        await engine.dispose()
