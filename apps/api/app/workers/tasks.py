"""Job definitions. Feature modules register their jobs in their own ``tasks.py`` from M1 onwards.

Rules (see CLAUDE.md): jobs take IDs (never ORM objects), re-fetch state, and are idempotent.
"""

import structlog

from app.workers.app import app

logger = structlog.get_logger(__name__)


@app.periodic(cron="*/5 * * * *", periodic_id="worker_heartbeat")
@app.task(queue="default", name="platform.heartbeat")
async def heartbeat(timestamp: int) -> None:
    """Proves the worker and scheduler are alive; alert if heartbeats stop."""
    logger.info("worker_heartbeat", scheduled_for=timestamp)
