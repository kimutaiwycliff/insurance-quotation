# Changelog

All notable changes are recorded here ([Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
commits follow Conventional Commits).

## [Unreleased]

### Added — M1 Identity, tenancy & platform core (2026-10-07)
- **Auth service** (`apps/auth`, Better Auth 1.7 on Hono, Node 24):
  - email/password with required verification and password reset;
  - optional Google sign-in;
  - organizations with invitations and agency roles;
  - TOTP 2FA;
  - EdDSA JWTs with JWKS;
  - bearer tokens;
  - organization hooks that mirror tenants and members into the API;
  - Compose services `auth-migrate` and `auth`.
- **Tenancy with Row-Level Security** (ADR-0003):
  - forced RLS on every tenant table;
  - composite FKs;
  - tenant id derived from the organization id;
  - a catalog guard test and a schema-drift test;
  - append-only audit log;
  - no hard deletes for `app_user`.
- **API authentication** (ADR-0006):
  - JWKS verification with cache and rotation handling;
  - membership mirror read on every request (removal is immediate);
  - lazy provisioning fallback;
  - service tokens for `/internal/*`.
- **Permissions** (ADR-0007): permission registry, agent-first default roles
  (owner/admin/agent/accounts/assistant/viewer), `require_permission` on every route, optional 2FA
  (enforceable per role through configuration).
- **Endpoints:**
  - `GET /api/v1/me`;
  - `GET/PATCH /api/v1/organization`;
  - `GET /api/v1/members`, `GET /api/v1/roles`;
  - branches CRUD with archive;
  - numbering schemes with preview;
  - `GET /api/v1/audit-events` with cursor pagination.
- **Platform services:**
  - idempotency keys in the request transaction, plus a purge job (ADR-0011);
  - `ETag`/`If-Match` optimistic concurrency;
  - Valkey rate limiting;
  - transactional job enqueue and domain events.
- **Money and currencies** (ADR-0008): `Money` type, ISO 4217 table.
- **Numbering** (ADR-0010):
  - gapless numbering per document type, branch and period;
  - M-Pesa-safe payment references with a check character.
- **Tests:**
  - 100+ unit tests;
  - integration tests for RLS, the permission matrix, idempotency races and 50-way concurrent numbering;
  - an end-to-end suite (`make e2e`) through the real auth service and Mailpit.
- **CI:** auth service job, auth image build and scan, E2E on `main`.
- **Docs:** ADR-0003/0006/0007/0008/0010/0011, architecture note, runbooks for key rotation and failed jobs.

### Added — M0 Foundations (2026-10-07)
- Spec review (`docs/SPEC_REVIEW.md`) and implementation plan (`docs/IMPLEMENTATION_PLAN.md`), including
  Amendment A1: Kenyan insurance agents are the target customer.
- API skeleton (FastAPI, Python 3.14):
  - app factory;
  - env-only settings;
  - structured JSON logging with secret/PII scrubbing;
  - request IDs;
  - RFC 9457 problem+json errors;
  - `/health/live` and `/health/ready` (Postgres, Valkey, storage);
  - Prometheus metrics;
  - optional Sentry.
- Procrastinate job runner on Postgres with a periodic heartbeat job (ADR-0004).
- Docker Compose stack: Postgres 18, Valkey 9, RustFS (S3), Mailpit, Gotenberg (hardened), migrate, api, worker.
  Least-privilege database roles (`app_owner`, `app_user`, `app_scanner`, `auth_owner`).
- Test stack (`make test`): tmpfs databases, migration up/down/up round-trip, parallel pytest with coverage gate.
- CI: lint, mypy --strict, import-linter, unit tests, OpenAPI drift and breaking-change checks, Compose suite,
  image and secret scanning. All actions are SHA-pinned.
- ADR-0001 (stack), ADR-0002 (agent-first sequencing), ADR-0004 (job runner), ADR-0005 (object storage).
