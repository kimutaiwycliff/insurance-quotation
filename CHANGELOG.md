# Changelog

All notable changes are recorded here ([Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
commits follow Conventional Commits).

## [Unreleased]

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
