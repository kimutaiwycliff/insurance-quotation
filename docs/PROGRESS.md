# Progress log & session handoff

Read this first when resuming work. Update it at the end of every session (newest entry on top).

## Current state (2026-10-07)
- **Done:** M0, M1 (branch `feat/m1-identity-tenancy`, not merged), **M2 platform services** on branch
  `feat/m2-platform-services` (stacked on M1). `make check`, `make test` (271 passed, 94.6% coverage) and
  `make e2e` are green.
- **Next:** W1 web foundation (sign-in/up, org, onboarding, settings incl. branding with live preview), or R1
  modules (M3+ per Amendment A1: clients, leads, insurers/products, quotes...). Plan §5–6.
- **M2 deviations (recorded in ADRs):**
  - 3 launch templates per the plan, not the spec's 8 (ADR-0014);
  - visual-diff PDF snapshots deferred, because rasterising PDFs needs new tooling;
  - stale pending uploads are not yet cleaned up (ADR-0023);
  - SES bounce/complaint webhooks deferred until the webhook ingress exists (ADR-0024);
  - premium template gating waits for SaaS billing.

## Decisions made
| Date | Decision | Where |
|---|---|---|
| 2026-10-07 | 2FA is **optional** for all roles (enforcement available through `MFA_ENFORCED_ROLES`, empty by default) | ADR-0007 |
| 2026-10-07 | M1 design: uuid5 tenant ids, per-request membership mirror, agent-first roles | ADR-0003/0006/0007 |
| 2026-10-07 | Target customer is **Kenyan insurance agents** (not brokers); Kenya only for now | Plan Amendment A1, ADR-0002 |
| 2026-10-07 | All plan recommendations approved: re-sequencing, Procrastinate, RustFS, Paystack-first, orval, Radix | ADR-0001/0002/0004/0005 |

## Still open (product owner / professionals)
- D1 legal entity (Kenyan only vs + foreign entity for Stripe/global tier)
- D4 tax adviser sign-off on KE pack values
- D5 lawyer opinion, including: may an agent represent several insurers per class?
- D6 hosting region (blocks `infra/` IaC + staging deploy)
- D7 brand, name and domain
- D8 prices and trial model
- Long-lead applications to start: KRA eTIMS integrator certification, ODPC registration, Paystack, Daraja, Meta (WhatsApp), Africa's Talking, SES.

## Known quirks / gotchas
- aiobotocore: iterate the `StreamingBody` wrapper (`body.iter_chunks`), not the value returned by
  `async with body as x` (that is the raw aiohttp response).
- Email: build messages with `email.policy.SMTP` and `max_line_length=998`, so long List-Unsubscribe URLs are not
  folded or encoded.
- Integration test clients get a random client IP (per-IP rate limits would otherwise collide across tests).
- Local Postgres host port is **55432** (5432 is used by a Postgres already installed on the dev machine).
- Docker image sets `PYTHONPATH=/app` (needed by the `procrastinate` CLI).
- The test environment uses `READINESS_TIMEOUT_SECONDS=5` (cold connections under 8 xdist workers).
- RustFS runs as uid 10001 (tmpfs mounts in tests set uid/gid).
- Upgrading Procrastinate requires a new Alembic revision with its migration SQL (ADR-0004).
- `.claude/settings.local.json` sets `ECC_GATEGUARD=off` (local only, git-ignored).
- CI has not run on GitHub yet: no remote is configured.
- Auth service uses **pnpm 11** (`packageManager`), which refuses packages younger than 1 day
  (`minimumReleaseAge`). Run installs with `CI=true` in scripts (no TTY). esbuild builds are disabled in
  `apps/auth/pnpm-workspace.yaml`.
- Better Auth's `signJWT` sets `iat` only if the payload has it; the API requires `iat`.
- Enabling 2FA rotates the Better Auth session (new `set-auth-token`).
- The `.test` TLD is rejected by `EmailStr`: use `example.com` in tests.
- `db.tenant_scope`/`session_scope` are async **context managers**. They used to be generators, and a
  `return` inside `async for` silently rolled the transaction back.

## Session log
### 2026-10-07: M2
- Made 2FA optional (ADR-0007) and committed M1 in 3 commits. Built M2: documents, rendering and templates,
  public links, email, notifications, migration 0003, ADR-0014/0023/0024, template guide and PDF runbook.
### 2026-10-07: M1
- Built the auth service, API auth/tenancy/RLS, permissions, audit, idempotency, concurrency, rate limiting,
  events, money, numbering, the E2E suite, ADRs and runbooks. Bugs found by tests and fixed: generator-based
  transaction scopes rolling back; ON CONFLICT target missing a second unique index; Luhn mod N with an odd
  alphabet.
### 2026-10-06 → 2026-10-07: review, plan, M0
- Reviewed `PROJECT_SPEC.md` with four research passes, then wrote `docs/SPEC_REVIEW.md` and `docs/IMPLEMENTATION_PLAN.md`.
- Moved the spec to `docs/PROJECT_SPEC.md` with an amendment banner.
- Built M0 and verified it with `make check`, `make test` (twice), `make audit` and `make up` (all 9 services healthy).
