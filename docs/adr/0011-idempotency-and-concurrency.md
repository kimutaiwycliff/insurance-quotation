# ADR-0011: Idempotency keys & optimistic concurrency

- Status: Accepted
- Date: 2026-10-07

## Decision
**Idempotency** (`app/platform/idempotency.py`). Creating endpoints accept `Idempotency-Key` (8–255 printable
ASCII characters).
- The key is claimed with `INSERT ... ON CONFLICT DO NOTHING` **in the request's transaction**. The response is
  stored in the same row before commit. Scope: tenant, principal, method, route template and key.
- A retry replays the stored status and body, plus `Idempotent-Replayed: true`. A concurrent retry blocks on the
  unique index until the first request commits, then replays: there is no "in progress" error and no double
  effect.
- The same key with a different body, method or path returns `422 idempotency_key_reused`. A failed request
  stores nothing, so the client can retry with the same key.
- Keys expire after `IDEMPOTENCY_TTL_HOURS` (24). A periodic job purges them through
  `app.purge_expired_idempotency_keys()` (ADR-0003 §8).

**Optimistic concurrency** (`app/core/concurrency.py`).
- Mutable resources carry `version` and return `ETag: W/"<version>"`. `PATCH` requires `If-Match`: missing
  returns `428 precondition_required`, stale returns `412 version_conflict`.
- SQLAlchemy's `version_id_col` adds `WHERE version = <old>` to the UPDATE, which closes the remaining race.

**Request transaction.** The tenant transaction commits when the endpoint returns, **before** the response is sent
(`Depends(..., scope="function")`), so a client never sees a success that later rolled back.

## Consequences
Every new create endpoint should take the idempotency dependency. W1's mutation helper sends a key by default.
