# CLAUDE.md — working rules for coding agents

**Product:** a SaaS for **Kenyan insurance agents** to manage clients, quotes, policies, renewals and commission and
to win more business, plus a standalone quotation & invoicing tier for SMEs. Kenya first; multi-country by design.

## Read before writing code (precedence when they conflict)
1. Accepted ADRs: `docs/adr/` (index in `docs/adr/README.md`)
2. `docs/IMPLEMENTATION_PLAN.md`: milestones, definition of done, test architecture (**Amendment A1 = agent-first**)
3. `docs/SPEC_REVIEW.md`: verified Kenyan regulatory facts and the corrections to the original spec
4. `docs/PROJECT_SPEC.md`: the original product spec

Current milestone: **R0 and R1.1–R1.5 done: the R1 agent MVP is complete** (CRM, insurers & premium engine, quotes, policies & renewals, commission & import). Next: pilot hardening, then R2. Slices: plan Amendment A1.1.
**Start every session by reading `docs/PROGRESS.md`** (handoff log); update it and `CHANGELOG.md` before ending.

## Non-negotiable rules
1. **Tenant isolation**: every tenant-owned table has `tenant_id`, RLS enabled and **forced**, the policy predicate
   `tenant_id = (SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid)` and composite FKs
   `(tenant_id, parent_id)`. The API connects as `app_user` (never the owner). Tests must prove cross-tenant access fails.
2. **Money is never a float**: `Decimal` in Python, `NUMERIC(20,4)` in Postgres, strings in JSON
   (`{"amount": "1234.50", "currency": "KES"}`). Round to the currency's ISO 4217 minor unit only in `app/core/money.py`.
3. **Issued financial records are immutable**: correct them with void, credit note or reversal. Never hard-delete.
4. **Jurisdiction rules are data**, never code: levies, taxes, WHT, numbering and statutory fields live in versioned,
   effective-dated packs. Kenyan values need adviser sign-off before seeding (see SPEC_REVIEW §2, §7).
5. **The platform never holds or settles client or tenant funds**: payments go to the tenant's (or insurer's) own
   merchant account.
6. **`app/calc` is pure** (no DB/HTTP/framework imports; enforced by import-linter). Modules talk through
   `service.py` functions or events, never each other's tables.
7. **Jobs** (Procrastinate) take IDs, re-fetch state and are idempotent. Enqueue inside the business transaction.
8. **Errors** are RFC 9457 problem+json via `app/core/errors.py` (subclass `AppError`; stable `code`).
9. **Config** only via `app/core/config.py` (env vars). Never log secrets, tokens or full PII.
10. **Everything runs in Docker Compose**. CI and the definition of done use `make test`.
11. **No secrets in the repo.** Document every new variable in `.env.example`.
12. **Ask before adding heavy dependencies** not in ADR-0001.
13. Conventional Commits; small focused changes; every milestone updates CHANGELOG, ADRs, docs and `openapi.json`.

## Commands
| Task | Command |
|---|---|
| Start stack | `make up` (API http://localhost:8000/docs, Mailpit http://localhost:8025, storage console http://localhost:9001) |
| Fast checks (no Docker) | `make check` (ruff, mypy --strict, import-linter, unit tests) |
| Definition of done | `make test` (migrations up/down/up + full suite + coverage ≥80% in Compose) |
| Format | `make fmt` |
| End-to-end (auth + API + Mailpit) | `make e2e` |
| Auth service checks | `make auth-check` |
| Web checks / browser E2E | `make web-check` / `make e2e-web` |
| Regenerate OpenAPI | `make openapi` (CI fails if `apps/api/openapi.json` is stale) |
| Dependency audit | `make audit` |

## Layout
```
apps/web/            Next.js 16.3 BFF + UI (pnpm 11): auth screens, onboarding, shell, settings
apps/auth/           Better Auth on Hono (Node 24, pnpm 11): users, orgs, 2FA, JWKS
apps/api/            FastAPI + Procrastinate (Python 3.14, uv)
  app/core/          config, logging, errors, middleware, db (no feature imports)
  app/platform/      health, resources, request deps (auth/tenant/permissions), audit, idempotency, events
  app/modules/       domain modules: models, schemas, service, router, tasks, events, README
  app/calc/          pure calculation engine
  app/integrations/  adapters behind Protocols (storage, payments, tax, messaging, pdf)
  app/workers/       job runner app and platform jobs
  migrations/        Alembic (runs as app_owner)
  tests/unit, tests/integration
infra/postgres/init  roles + schemas (superuser, first boot only)
docs/                spec, review, plan, ADRs, runbooks
```

## Definition of done (per change)
Migration (+ explicit RLS) · unit + integration tests · tenancy and permission tests for tenant endpoints ·
`make check` and `make test` green · `make openapi` · docs/ADR/CHANGELOG/.env.example updated.
