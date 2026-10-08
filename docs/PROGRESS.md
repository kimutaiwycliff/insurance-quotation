# Progress log & session handoff

Read this first when resuming work. Update it at the end of every session (newest entry on top).

## Current state (2026-10-08)
- **Done:**
  - R0 (M0–M2, W1);
  - **R1.1 agent CRM**, committed on `feat/r1-clients-leads`.
- **Next: R1.4** policy book (insurer-direct collection), renewal board, reminders (email + WhatsApp click-to-chat).
- **Done: R1.2** (insurers, premium engine, KE pack pending sign-off, calculator) on `feat/r1-2-insurers-calc`
  (stacked, not merged, no remote). The notes below describe what it contains.
  - Backend done and tested, not yet committed at the time of writing:
    - `app/calc/pack.py` (pack model) and `app/calc/premium.py` (pure engine);
    - `app/jurisdictions/` (YAML packs `ke/2026.1` *pending sign-off*, `generic/2026.1`, loader);
    - golden scenarios `tests/golden/ke_premium.yaml` (14, hand-calculated, awaiting D4);
    - `app/modules/insurers` (insurers, products, `/jurisdiction-pack`, `/premium/calculate`,
      `/premium/compare`; commission hidden without `commission:read:*`);
    - migration 0005.
  - Web: Settings → Insurers & products, Premium calculator (Playwright journey green).
- **Done: R1.3 insurance quotes** on `feat/r1-3-quotes` (stacked, not merged). Built as planned:
  - **Backend** `app/modules/quotes`: Quote (client, class, risk snapshot, status draft|sent|accepted|declined|
    withdrawn, valid_until, number allocated on first send) and QuoteOption (product snapshot, breakdown
    JSON, client_total, internal commission JSON, position, recommended).
    - Create and recalculate via `insurers.service.calculate_product`.
    - Send: number, comparison PDF (DocumentView gets `options`), public link scopes view+accept, emailed.
      Register public target "quote" with html, download and choices.
    - Public accept and decline by option *position* (no ids), with acceptance evidence. Notify the owner;
      a linked lead goes to "quoted" on send.
    - Tenant flag `multi_insurer_quotes` (D5).
  - **Web:** quotes list, new quote from the client page, quote detail with send and withdraw; public page
    `/d/[token]` through a `/public-api` proxy (iframe html, download, accept/decline, view beacon).
  - **Test:** commission never appears in public HTML or PDF.
- **Env:** the `cadaster-upload` containers were stopped (with the user's OK) for Docker headroom. Restart:
  `docker start cadaster-upload_postgres cadaster-upload_minio cadaster-upload_redis`.

## Decisions made
| Date | Decision | Where |
|---|---|---|
| 2026-10-08 | R1 delivered in slices R1.1–R1.5; agents see only their own clients, leads and tasks | Plan A1.1, ADR-0007 |
| 2026-10-08 | ID/passport numbers encrypted in the application with keyed-hash lookup | ADR-0018 |
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
- YAML 1.1: keys like `on`, `yes` and `no` parse as booleans (the pack field is `signed_on`, not `on`).
- Money and rates never accept JSON numbers: `AmountStr`/`RateStr` carry `NoFloat` (422 on floats).
- Pydantic `StringConstraints(to_upper=True, pattern=...)` checks the pattern *before* upper-casing; patterns
  must accept both cases.
- Scope helpers use a TypeVarTuple (`def _scoped[*Ts](stmt: Select[*Ts], ...)`) so aggregate selects type-check.
- Web: never use `crypto.randomUUID()` (missing on plain-HTTP origins such as http://web:3000 in E2E); use
  `randomId()`.
- Web: next-intl messages use ICU, so escape literal braces with apostrophes (`'{YYYY}'`).
- Web: axe cannot scan sandboxed iframes; the E2E helper excludes `iframe[sandbox]`.
- shadcn CLI once rewrote the `cn` import to an npm package named `cn` and installed it. Check `package.json`
  after running `shadcn add`.
- Docker Desktop disk: prune old build cache (`docker builder prune --filter until=72h`) if builds hit ENOSPC.
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
### 2026-10-08: R1.1
- Agent CRM backend (clients, households, contacts, activities, leads, tasks, dashboard, migration 0004,
  PII crypto, phone normalisation) and screens (clients, client 360°, leads board, tasks, dashboard).
### 2026-10-07: W1
- Built the web app (auth, onboarding, shell, settings, branding preview), the BFF, the orval client, Vitest/MSW
  tests and the Playwright and axe golden path. Fixed along the way: creating an organization did not set it
  active; `randomUUID` on insecure origins; Sonner toast contrast; axe hanging on sandboxed iframes.
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
