# ADR-0003: Tenancy & Row-Level Security model

- Status: Accepted
- Date: 2026-10-07

## Context
Every agency's clients, policies and money must be invisible to every other agency, including when application
code has a bug. The original spec's RLS policy threw instead of filtering, child tables lacked `tenant_id`, and
FKs could point across tenants (SPEC_REVIEW §4.1).

## Decision
1. **Shared schema, row-level isolation.** Every tenant-owned table in schema `app` has `tenant_id`, RLS
   **enabled and forced**, and one policy `tenant_isolation`:
   `tenant_id = (SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid)` for `USING` and `WITH CHECK`.
   An unset context matches no rows. DDL helpers live in `app/core/rls.py`.
2. **Tenant context per transaction.** `set_config('app.tenant_id', <id>, true)` (transaction-local) at the start
   of every request transaction, job and internal call. It cannot leak to the next user of a pooled connection.
3. **Roles.** The API and workers connect as `app_user` (no ownership, no `BYPASSRLS`). Migrations run as
   `app_owner`. RLS is forced, so it also applies to the owner.
4. **Composite FKs.** Tenant tables expose `UNIQUE (tenant_id, id)`; children reference `(tenant_id, parent_id)`.
   FK checks bypass RLS, and this is what stops a row pointing at another tenant's parent.
5. **Tenant id = `uuid5(TENANT_NAMESPACE, better_auth_org_id)`.** The API derives the RLS context directly from
   a verified token, so it never needs a lookup that bypasses RLS. `tenants.auth_org_id` keeps the source id.
   `tenants` is itself under RLS (key column `id`).
6. **No global user table.** Name and email of a user live on the tenant-scoped `memberships` row (the
   membership mirror), so every table holding personal data is under RLS.
7. **Global tables** are an explicit allow-list (`GLOBAL_TABLES`: `currencies`, `alembic_version`) and are
   read-only to `app_user`.
8. **Cross-tenant maintenance** uses narrow `SECURITY DEFINER` functions owned by `app_owner`, with a policy
   scoped `TO app_owner` that only matches the rows the function may touch. Example:
   `app.purge_expired_idempotency_keys()`. Broad `BYPASSRLS` is never granted.
9. **Guard rails.** A catalog guard test fails CI if a table in `app` is not allow-listed and lacks forced RLS,
   the exact predicate, or a tenant-scoped FK. A schema-drift test compares the migrated database with the ORM
   models. `app_user` has no `DELETE` on tenant root tables (archive instead) and no `UPDATE`/`DELETE` on the
   audit log.

## Consequences
- Migrations are hand-written: autogenerate cannot see policies or grants. The DDL is frozen in the migration
  file, and the drift test catches mismatches.
- Tests isolate by creating fresh organizations per test (RLS keeps them apart) instead of rolling back
  transactions. This replaces the per-worker template database in plan §3.2, which is simpler and exercises
  RLS for real.
- If the identity provider ever changes, new tenants can use a new namespace; existing ids stay valid.
