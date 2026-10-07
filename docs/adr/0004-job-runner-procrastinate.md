# ADR-0004: Job runner — Procrastinate on Postgres

- Status: Accepted (2026-10-07)
- Supersedes: Celery + Celery Beat + Redis broker (`docs/PROJECT_SPEC.md` §4.3, §5.4)

## Context
The spec paired an async API with sync Celery tasks "using one driver" and an outbox table dispatched by Beat. That
design forces duplicated service code or `asyncio.run()` per task. It also needs separate outbox-dispatch machinery,
and it inherits Redis-broker caveats: no native dead-letter queue, and `visibility_timeout` vs ETA duplicates.

## Decision
- Use **Procrastinate 3.10** with the psycopg connector. Jobs live in Postgres schema `jobs`.
- **Enqueue jobs inside the business transaction.** This makes job dispatch atomic with the state change, which is the transactional outbox.
- Periodic jobs use `@app.periodic`. The worker runs from the same image (`procrastinate --app=app.workers.app.app worker`).
- Queues: `default`, `pdf`, `messaging`, `webhooks`, `imports`, `tax`.
- Jobs take IDs, re-fetch state, are idempotent, and use retries with backoff. Permanently failed jobs remain in `procrastinate_jobs` with status `failed` and are surfaced in the admin API (M1).
- Valkey remains for caching and rate limiting only.

## Consequences
- The Procrastinate schema is created by Alembic revision `0001` from the installed version's `SchemaManager.get_schema()`. **Upgrading Procrastinate requires a new Alembic revision applying its migration SQL**, checked in CI.
- `app_user` has DML and EXECUTE on schema `jobs` and `search_path = app, jobs, public`, so the API can enqueue.
- Throughput is ample for this workload. If it isn't, the queue adapter is isolated in `app/workers`.
