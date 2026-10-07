"""Transactional job enqueue and domain events (ADR-0004).

Jobs live in Postgres, so deferring a job through the *request's own session* makes the enqueue atomic with the
business change: if the transaction rolls back, the job never existed. This is the outbox.

Events fan out at publish time: every subscriber of an event gets its own job, so one slow or failing subscriber
never blocks another and each retries independently. Subscribers are Procrastinate tasks registered with
:func:`subscribe`; they receive ``tenant_id`` and the payload, must re-fetch state and be idempotent.
"""

import json
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_SUBSCRIBERS: defaultdict[str, list[tuple[str, str]]] = defaultdict(list)

_DEFER_SQL = text(
    "SELECT unnest(jobs.procrastinate_defer_jobs_v1(ARRAY[ROW("
    ":queue, :task_name, :priority, :lock, :queueing_lock, CAST(:args AS jsonb), now()"
    ")::jobs.procrastinate_job_to_defer_v1]))"
)


async def enqueue(
    session: AsyncSession,
    task_name: str,
    args: dict[str, Any],
    *,
    queue: str = "default",
    priority: int = 0,
    lock: str | None = None,
    queueing_lock: str | None = None,
) -> int:
    """Defer a job inside the current transaction. Returns the job id."""
    result = await session.execute(
        _DEFER_SQL,
        {
            "queue": queue,
            "task_name": task_name,
            "priority": priority,
            "lock": lock,
            "queueing_lock": queueing_lock,
            "args": json.dumps(args, default=str),
        },
    )
    return int(result.scalar_one())


def subscribe(event_name: str, task_name: str, *, queue: str = "default") -> None:
    """Register a Procrastinate task (by name) to run for every ``event_name``."""
    entry = (task_name, queue)
    if entry not in _SUBSCRIBERS[event_name]:
        _SUBSCRIBERS[event_name].append(entry)


def subscribers(event_name: str) -> list[tuple[str, str]]:
    return list(_SUBSCRIBERS.get(event_name, ()))


async def publish(
    session: AsyncSession, event_name: str, tenant_id: uuid.UUID, payload: dict[str, Any]
) -> list[int]:
    """Publish a domain event in the current transaction; returns the ids of the subscriber jobs."""
    event_id = str(uuid.uuid7())
    return [
        await enqueue(
            session,
            task_name,
            {
                "event_id": event_id,
                "event": event_name,
                "tenant_id": str(tenant_id),
                "payload": payload,
            },
            queue=queue,
        )
        for task_name, queue in subscribers(event_name)
    ]
