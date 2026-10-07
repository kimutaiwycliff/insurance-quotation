# Progress log & session handoff

Read this first when resuming work. Update it at the end of every session (newest entry on top).

## Current state (2026-10-07)
- **Done:** M0 Foundations (repo, Compose stack, API skeleton, job runner, CI, docs). `make test`: 23 passed, 96.8% coverage.
- **Next:** **M1 — identity, tenancy & platform core** (docs/IMPLEMENTATION_PLAN.md §5, M1):
  - Better Auth service in `apps/auth` (email/password + Google, organization, 2FA, JWT/JWKS, bearer);
  - JWKS verification in the API;
  - tenant provisioning (hook + lazy);
  - RLS framework + catalog guard test;
  - permission registry and roles (agent-focused);
  - audit log;
  - idempotency keys;
  - optimistic concurrency;
  - org settings and branches;
  - gapless numbering and `payment_reference`;
  - currency table/Money type;
  - ADR-0003, 0006, 0007, 0010, 0011.
- **Then:** W1 web foundation, M2 platform services, then R1 Agent MVP (ADR-0002).

## Decisions made
| Date | Decision | Where |
|---|---|---|
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
- Local Postgres host port is **55432** (5432 is used by a Postgres already installed on the dev machine).
- Docker image sets `PYTHONPATH=/app` (needed by the `procrastinate` CLI).
- The test environment uses `READINESS_TIMEOUT_SECONDS=5` (cold connections under 8 xdist workers).
- RustFS runs as uid 10001 (tmpfs mounts in tests set uid/gid).
- Upgrading Procrastinate requires a new Alembic revision with its migration SQL (ADR-0004).
- `.claude/settings.local.json` sets `ECC_GATEGUARD=off` (local only, git-ignored).
- CI has not run on GitHub yet: no remote is configured.

## Session log
### 2026-10-06 → 2026-10-07: review, plan, M0
- Reviewed `PROJECT_SPEC.md` with four research passes, then wrote `docs/SPEC_REVIEW.md` and `docs/IMPLEMENTATION_PLAN.md`.
- Moved the spec to `docs/PROJECT_SPEC.md` with an amendment banner.
- Built M0 and verified it with `make check`, `make test` (twice), `make audit` and `make up` (all 9 services healthy).
