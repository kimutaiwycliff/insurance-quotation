# Implementation Plan — Production-Grade Build of the Broker & Invoicing SaaS

> Version 1 · 2026-10-06 · Inputs: `PROJECT_SPEC.md` + [`SPEC_REVIEW.md`](SPEC_REVIEW.md) (all corrections applied here).
> Audience: product owner, tech lead, and the Claude Code agents doing the build.
> Items tagged **(D#)** depend on a decision in SPEC_REVIEW §7. Where a decision is pending, this plan uses the
> recommended default and the work is arranged so the decision can land later without rework.

---

## 0. Amendment A1 (2026-10-07): agent-first, Kenya only. Supersedes conflicting parts of §1, §6–§8.

The product owner confirmed the insurance tier targets **Kenyan insurance agents** who want to manage clients well and win
more business, not brokers. All plan recommendations (D2 re-sequencing, D3 Procrastinate, RustFS, Paystack-first, orval,
Radix) are **approved**. Consequences:

| Area | Change |
|---|---|
| Release order | **R1 = Agent MVP** (insurance CRM). **R2 = Invoicing tier + online payments + eTIMS.** **R3 = Growth & automation.** Foundations (M0–M2, W1) are unchanged. |
| R1 scope | Clients & households 360°; **leads/pipeline** (pulled forward from P2 — agents want more clients); insurers & products (light); insurance quotes with multi-insurer comparison and KE levy/stamp-duty calc; policy book (`insurer_direct` collection by default: client pays the insurer); **renewal board + reminders** (email + WhatsApp click-to-chat links; Cloud API in R3); tasks & follow-ups; **commission tracking** (expected vs received, **10% WHT** for resident agents); KYC/document vault with expiry; dashboard; spreadsheet import of the existing book. |
| Deferred (broker-only) | Premium trust account, remittance batches, INS 153‑1 return, statement reconciliation, agent/sub-agent split hierarchies → only if brokers become a target. The model keeps `collection_mode` so `broker_collects` can be added later without migration pain. |
| Premium handling | Agents may collect premium only if the insurer authorises it, and must remit **"immediately"** (Regs r.42). R1 records insurer-direct payments and agent-collected payments with a remittance-due alert (same day). |
| eTIMS | Agents' commission is paid by insurers. Small agents (turnover ≤ KES 5m) may be **reverse-invoiced by the insurer** (TPA s.23A(3A)), so agent-side eTIMS moves to R2 together with the Invoicing tier. Confirm with the tax adviser (D4). |
| Growth features | R3: client portal (policy wallet), referral links, WhatsApp Cloud API automation, birthday/anniversary nudges, cross-sell suggestions (e.g. motor client without medical), AI extraction of insurer schedules (huge typing saver for agents), Expo mobile app (agents work from phones — mobile-first web is mandatory from R1). |
| Pricing hypothesis | Individual-agent plan ~KES 1,500–3,000/mo; small agency (≤5 seats) ~KES 5,000–10,000; free capped tier or 30-day trial; M‑Pesa payment for subscriptions. |
| Open verification | Whether a Kenyan agent may hold appointments with several insurers per class. This decides whether multi-insurer comparison quotes are an agent use case or need a different framing. **Ask the lawyer (D5) / IRA.** |

### A1.1 R1 delivery slices (2026-10-08)
Each slice ships backend first (API + tests), then its screens (web + Playwright).

| Slice | Scope | Blocked by |
|---|---|---|
| **R1.1** | Clients & households (360° timeline, KYC documents, notes/calls, encrypted IDs, duplicates, agent scoping), leads pipeline + conversion, tasks & reminders, dashboard v1 | — |
| R1.2 | Insurers & products (light), calc engine v1, KE jurisdiction pack (values flagged *pending sign-off*) | D4 for real values |
| R1.3 | Insurance quotes: multi-insurer comparison, KE levies/stamp duty, send via tracked link, accept | R1.2; D5 (multi-insurer framing) |
| R1.4 | Policy book (insurer-direct collection), renewal board, reminders (email + WhatsApp click-to-chat) | R1.3 |
| R1.5 | Commission tracking (expected vs received, 10% WHT), spreadsheet import of the book, dashboard v2 | R1.4 |

### A1.2 R2 delivery slices (2026-10-08)
R2 = invoicing tier + online payments + eTIMS (plan §6 M3–M5, W2–W3), on top of what R1 already built (clients,
numbering, rendering, public links, email, tasks, imports). Each slice ships API, screens and tests through a
pull request with all CI checks green (`main` is protected).

| Slice | Scope | Blocked by |
|---|---|---|
| **R2.1** | Invoicing core: item catalogue; invoices and credit notes (lines, VAT inclusive/exclusive, discounts, pack tax codes); issue (number, payment reference, immutable once issued), void; manual payments with allocation and client credit; numbered receipts; double-entry ledger; PDF, tracked link and email | — |
| R2.2 | Sales quotes for SMEs (sections, optional items, accept, convert to invoice); reminder rules (invoice due/overdue, quote expiring); invoicing dashboard | R2.1 |
| R2.3 | Online payments: payment connections, Paystack (tenant's own account), webhook ingress, pay from the public link | R2.1; Paystack test keys |
| R2.4 | KE invoicing pack values and eTIMS: `manual_reference` stopgap, then the OSCU adapter against the KRA sandbox | D4; KRA sandbox access |
| R2.5 | M-Pesa Daraja direct (STK Push, C2B, unmatched queue, reconciliation) | R2.3; Daraja sandbox |
| R2.6 | SaaS plans, entitlements and our own subscription billing | D8 prices |

### A1.3 R2 re-sliced after product decisions (2026-10-08)
Decisions: payments by **M-Pesa Daraja only** (cards shown as "coming soon", Paystack on hold; ADR-0015);
**eTIMS optional** with a manual reference (ADR-0017); hosting on **one VM with Docker Compose**
(ADR-0020); plans per `docs/PRICING.md` (D8, proposal); name and domain still open (D7). R2.1 and R2.2 are
done. Remaining R2 slices replace A1.2 rows R2.3–R2.6:

| Slice | Scope | Blocked by |
|---|---|---|
| **R2.3** | M-Pesa Daraja: tenant connections (encrypted), STK Push from the invoice link and the app, STK Query confirmation, C2B confirmation and validation, unmatched-payments queue, daily reconciliation; cards "coming soon" | Daraja sandbox keys for the sandbox smoke test only |
| R2.4 | Optional eTIMS: tenant toggle, manual CU number and QR on invoices and credit notes | — |
| **R2.5** ✅ | Plans and entitlements (Free / Agent / Agency / Business), 30-day trial, M-Pesa subscription billing on the platform shortcode, founding-member offer (done 2026-10-09, ADR-0025); referrals, renewal reminders and our own receipts follow as R2.5b | — |
| **R2.6** ✅ | Production on a VM (done 2026-10-09; awaiting the VM): `compose.prod.yaml` with Caddy TLS, backups and restore drill, deploy and rollback runbook, monitoring | D7 domain to go live |

---

## 1. Strategy in one page

1. **Release in three commercial increments, built in vertical slices.**
   - **R1 Invoicing**: quotes, invoices, receipts, payments, eTIMS, templates and public links for SMEs and agents. Kenya + generic pack.
   - **R2 Broker MVP**: insurers, products, insurance quotes, policies, debit notes, s.156-aware premium handling, commissions, remittances, renewals.
   - **R3 Broker Pro**: endorsements and cancellations, statement reconciliation, SMS/WhatsApp, imports, full reports, custom roles.
   - **Later (P2/P3)**: claims, client portal, leads, mobile, admin console UI, reinsurance, AI.
2. **Backend-first per slice (D2).** For each slice, the API is complete, tested in Compose and its OpenAPI committed before its UI starts. UI work trails the backend by one milestone, so the web app exists from R1.
3. **Compliance before cleverness.** The KE pack, eTIMS and premium-handling rules are on the critical path. Long-lead external processes (KRA integrator certification, ODPC, Meta, Paystack, Safaricom) start in week 1.
4. **Platform invariants never bend.** Tenant isolation proven by tests; money is `Decimal`; issued financial records are immutable; **the platform never holds or settles funds**; jurisdiction rules are data.
5. **Production-grade from M0.** CI, security scanning, observability, migrations, backups and runbooks are built in the first milestones, not bolted on at the end.

### Release map

| Release | Milestones (backend → web) | Exit criterion |
|---|---|---|
| R0 Foundations | M0, M1, M2 → W1 | A user can sign up, create an org and see an empty, themed app; all platform services are green in Compose and CI |
| **R1 Invoicing** | M3, M4, M5 → W2, W3 | 5–10 pilot SMEs/agents issue eTIMS-compliant invoices, send tracked links and get paid via Paystack/M‑Pesa; paid SaaS subscriptions live |
| **R2 Broker MVP** | M6, M7, M8, M9 → W4, W5 | 3–5 pilot brokers run quote → policy → debit note → collection → remittance → commission end to end for motor and medical |
| **R3 Broker Pro** | M10, M11, M12 → W6 | Endorsements/cancellations, reconciliation, multi-channel reminders, imports, full reports; hardening complete; general availability |
| R4+ | P2/P3 backlog (§9) | — |

**Rough effort** (assumes 2–3 senior engineers working with AI agents and a part-time designer; ±40%): R0 ≈ 5–7 weeks, R1 ≈ 8–10 weeks, R2 ≈ 10–12 weeks, R3 ≈ 8–10 weeks. External approvals (KRA certification, Meta) may gate dates independently of engineering.

---

## 2. Corrected architecture baseline

| Concern | Decision |
|---|---|
| Backend | Python **3.14**, uv, FastAPI 0.142+ (`fastapi[standard]`), Pydantic 2.13, SQLAlchemy **2.1** + Alembic 1.20, psycopg 3.3 (async) |
| DB | **PostgreSQL 18** (`uuidv7()`, SCRAM), extensions `pg_trgm`, `citext`; schemas `app`, `auth` |
| Jobs | **Procrastinate** (D3) on Postgres, with periodic tasks and transactional enqueue. Fallback: Celery 5.6 with a dedicated outbox dispatcher |
| Cache / rate limiting | **Valkey 9** |
| Object storage | Dev/CI: **RustFS** (Garage fallback); prod: AWS S3 or Cloudflare R2. Plain S3 API via aioboto3 |
| PDF | Gotenberg 8.37, hardened (deny private IPs, allow-list, JS off), internal network only |
| Email | Dev: Mailpit 1.31. Prod: **Amazon SES with tenant management** (Postmark alternative) |
| Auth | **Better Auth 1.7.x** on Hono 4, Node 24, Postgres schema `auth`; JWT (EdDSA, JWKS at `/api/auth/jwks`, 15 min) |
| Payments | Adapters: `fake`, **`paystack`** (tenant's own account), **`mpesa_daraja`** (advanced), `stripe_connect` (only if D1 creates a foreign entity) |
| SaaS billing | `fake`, **`paystack_billing`** (cards) + M‑Pesa renewal flow; `stripe_billing` only if D1 |
| Tax | `noop`, `fake`, `manual_reference` (stopgap), **`kra_etims_oscu`** (after certification) |
| Messaging | Email adapter (SMTP/SES); SMS `africastalking` (R3); WhatsApp `whatsapp_cloud` (R3) |
| Frontend | Next.js **16.3.x** (`proxy.ts`), React 19.3, TS strict (6.x for tooling until 7.1), Tailwind 4.3, **shadcn CLI v4** (primitive per D11; recommend Radix for ecosystem maturity), TanStack Query 5, TanStack Table **v8**, react-hook-form + **zod 4**, next-intl, next-themes, sonner, Recharts 3 |
| API client | **orval 8** → `packages/api-client` (types, React Query hooks, zod, MSW mocks) |
| Monorepo | pnpm 12 workspaces (with catalogs) + Turborepo 2.11; uv for Python |
| CI | GitHub Actions, **every action SHA-pinned**, least-privilege `permissions:`, OIDC to cloud |
| Prod hosting (D6, recommended default) | Managed containers + managed Postgres 18 with PITR + managed Valkey + S3 in one cloud region. Health-data residency handled by consent capture (DPA s.48–49) unless D6 chooses in-country hosting. Infrastructure as code (OpenTofu). |

### Architectural invariants (CI-enforced where possible)
1. Every table in schema `app` is tenant-scoped (with `tenant_id`, RLS enabled + forced, policy, composite FKs) or on `GLOBAL_TABLES_ALLOWLIST`. Enforced by catalog guard test.
2. RLS predicate: `tenant_id = (SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid)`.
3. Only `app/calc` does premium/levy/tax/commission arithmetic, and it is pure. Enforced by import-linter: `app.calc` imports nothing from `app.modules`, `app.integrations` or `sqlalchemy`.
4. Modules call other modules only via `service.py` public functions or events. Enforced by import-linter contracts.
5. Money columns `NUMERIC(20,4)`; rounding to the ISO 4217 minor unit happens only in `app/core/money.py`.
6. No code path moves funds into a platform-owned account. Payment adapters are configured only with tenant credentials. Reviewed in the security checklist.
7. Issued financial rows are immutable: DB trigger blocks UPDATE of financial columns when `status <> 'draft'`, plus `REVOKE UPDATE, DELETE` on audit and ledger tables.

---

## 3. Cross-cutting engineering standards (apply to every milestone)

### 3.1 Definition of Done (revised from spec §0.3)
- [ ] Alembic migration(s), reversible where practical, with up/down tested in CI. RLS policies written explicitly (alembic-utils `PGPolicy` or `op.execute`).
- [ ] Catalog guard test, import-linter and permission-registry tests are green.
- [ ] Unit tests (domain, calc, state machines). Integration tests on real Postgres, Valkey, RustFS, Mailpit and Gotenberg. RLS tests and permission-matrix tests for new endpoints.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` (2.x); for TS, `eslint`, `tsc --noEmit`, `prettier --check`.
- [ ] Coverage: **≥95% on `app/calc`**, ≥90% on `app/core`, ≥85% on `app/modules/**/service.py`, **≥80% on `app/` overall**. Branch coverage on.
- [ ] `openapi.json` regenerated and committed; **oasdiff** reports no unapproved breaking changes; `packages/api-client` regenerated with no diff.
- [ ] `make test` passes (`docker compose -f compose.yaml -f compose.test.yaml run --rm api-tests`).
- [ ] Docs: module `README.md`, ADR(s), `.env.example`, `CHANGELOG.md`, runbook entries for new operational surfaces.
- [ ] Security: new endpoints declare a permission and a rate-limit class; new external inputs are validated; no secrets or PII in logs (log-scrubbing test).

### 3.2 Test architecture

| Layer | Tooling | Scope | Gate |
|---|---|---|---|
| Unit | pytest 9, hypothesis, time-machine | calc, state machines, numbering formatter, permission registry, money, pack loader | every PR |
| Golden calc | YAML fixtures signed by accountant (D4) | ≥40 KE scenarios (motor private/commercial, medical, fire, marine, life stamp duty, WIBA, pro-rata, short-period, leap year, min-premium, WHT broker/agent) | every PR; changes need a CODEOWNERS approval |
| Property | hypothesis | totals = Σ components; non-negative unless credit; splits ≤ base; rounding idempotent; per-currency balance | every PR |
| Integration | pytest-asyncio 1.x, httpx ASGI, factory-boy, respx | services + API + DB + Valkey + RustFS + Mailpit + Gotenberg | every PR (Compose) |
| Tenancy | dedicated suite | A-vs-B for list/get/update/delete on every tenant route, auto-generated from the router table; raw SQL as `app_user` with no context → 0 rows; composite-FK cross-tenant insert → error | every PR |
| Permissions | generated matrix | role × endpoint from the registry; expected 2xx/403 | every PR |
| Concurrency | committing tests | 50 parallel issues → gapless and unique; double webhook → one payment; idempotency race | every PR |
| Contract | schemathesis 4 (`from_asgi`, `schemathesis.toml`), authenticated fixtures, stateful links | no 5xx, schema conformance | every PR (time-boxed); nightly full |
| E2E API | pytest against live auth + api in Compose | golden paths per release | merge to main |
| Web unit | Vitest + Testing Library + MSW (orval mocks) | components, forms, error mapping | every PR |
| Web E2E | Playwright in Compose, axe-core | golden paths via UI, a11y (WCAG 2.2 AA), mobile viewport | merge to main |
| Templates | HTML snapshots + PDF via Gotenberg + pypdf text assertions + visual diff | every template × doc type × fixture set (long names, 150 lines, 0-dp currency, RTL text) | every PR touching templates |
| Migrations | upgrade from previous release's schema snapshot with seeded data, then downgrade | every PR with migrations |
| Performance | Locust (needs approval as a dependency) or a custom httpx load script | p95 < 300 ms core list/get with a 50k-policy tenant; PDF throughput | per release |
| Security | ZAP baseline (Compose), pip-audit, osv-scanner v2, Trivy (pinned), gitleaks, Semgrep | nightly + release |

**DB fixture design:**
- A session-scoped fixture migrates a template DB once.
- Each xdist worker gets `CREATE DATABASE test_{worker} TEMPLATE app_template`.
- Default test fixture: a connection-level transaction plus nested SAVEPOINTs, rolled back at the end.
- `@pytest.mark.committing` tests use real commits and truncate tenant tables afterwards.
- RLS tests connect as `app_user` explicitly. Jobs run in-process via a test worker helper.

### 3.3 Documentation system

| Artifact | Location | Owner | When |
|---|---|---|---|
| Agent rules | `/CLAUDE.md` (≤150 lines; links to spec, review, plan, ADR index) | tech lead | M0 |
| Spec (living) | `docs/PROJECT_SPEC.md`, amended per SPEC_REVIEW; changes via PR | product owner | M0 |
| Architecture | `docs/architecture/` (C4 context/container/component diagrams in Mermaid, data-flow diagrams for money and PII, tenancy model) | tech lead | M0–M2 |
| ADRs | `docs/adr/NNNN-*.md` (index in `docs/adr/README.md`) | author of change | continuous |
| Module READMEs | `apps/api/app/modules/*/README.md`: purpose, entities, state machine diagram, permissions, events emitted/consumed, jobs | module author | per milestone |
| Jurisdiction packs | `docs/jurisdictions/ke.md`: every value with legal source, effective date and sign-off record | compliance owner | M5, M7 |
| API reference | OpenAPI 3.1 served via Scalar/Redoc at `/docs` (internal), plus a published static copy per release | CI | continuous |
| Runbooks | `docs/runbooks/`: deploy, rollback, migrations, restore from backup, key rotation, webhook replay, failed jobs, eTIMS outage, payment provider outage, incident response, data-subject requests, breach notification (72 h/48 h) | on-call | before each release |
| Compliance | `docs/compliance/`: ROPA, DPIA (health data), retention schedule, processor agreement template, sub-processor list, ODPC registration record, ASVS L2 checklist | DPO / tech lead | R1 |
| User help | `apps/web` help centre (MDX) + in-app empty states | product | R1+ |
| Changelog | `CHANGELOG.md` (Keep a Changelog; generated from Conventional Commits) | CI | continuous |
| Repo hygiene | `SECURITY.md`, `CONTRIBUTING.md`, PR template with DoD checklist, CODEOWNERS (calc, packs, migrations, auth) | tech lead | M0 |

**ADR backlog** (write when the milestone starts):
0001 stack · 0002 release sequencing · 0003 tenancy & RLS model · 0004 job runner · 0005 object storage (RustFS/S3) · 0006 auth topology & JWT/BFF flow · 0007 roles & permissions source of truth · 0008 money, currencies & rounding · 0009 document state model (orthogonal statuses) · 0010 numbering & payment references · 0011 idempotency · 0012 ledger chart of accounts · 0013 jurisdiction pack format & loader · 0014 template rendering & public-page isolation · 0015 payment provider strategy & "no funds held" invariant · 0016 webhook ingress & tenant routing · 0017 eTIMS integration & stopgap · 0018 PII encryption & key management · 0019 premium collection modes & activation gating · 0020 hosting & data residency · 0021 frontend data-fetching & BFF · 0022 API client codegen.

---

## 4. Phase 0 — Decisions & long-lead items (week 1, runs alongside M0)

| # | Action | Output |
|---|---|---|
| 0.1 | Product owner decides D1, D2, D6, D7 (and D3, D11 by tech lead) | ADR-0001/0002/0020 updated |
| 0.2 | Engage Kenyan tax adviser + insurance lawyer (D4, D5); hand them SPEC_REVIEW §2 and §7 | Engagement letters; golden-example workbook started |
| 0.3 | **Start KRA eTIMS third-party integrator process**: sandbox access, prerequisite documents (tax compliance certificate, technical staff CVs, architecture document) | Application submitted |
| 0.4 | ODPC registration (processor); appoint DPO; draft DPIA for health data | Registration filed |
| 0.5 | Paystack business account (our billing) + test accounts; Daraja developer account; Africa's Talking account; SES account + domains (SPF/DKIM/DMARC) | Credentials in secrets manager |
| 0.6 | Meta Business verification (for R3 WhatsApp) | Verification submitted |
| 0.7 | Recruit pilots: 5–10 SMEs/agents (R1), 3–5 brokers (R2), e.g. via AIBK | Pilot list + interview notes |
| 0.8 | Design: brand direction, 3 launch templates, core screen wireframes (onboarding, quote builder, public document page) | Figma / design tokens |

---

## 5. R0 — Foundations

### M0 · Repository, tooling, CI, environments
**Scope**
- Monorepo layout per spec §4.4, adjusted: `apps/api`, `apps/auth`, `apps/web` (scaffold only), `packages/api-client`, `packages/config`, `infra/` (OpenTofu), `docs/`.
- `apps/api`: app factory, pydantic-settings config, structlog JSON logging with request-ID middleware, RFC 9457 error handlers (`code` + `errors[]`), `/health/live` and `/health/ready`, `/metrics` on an internal port, OpenTelemetry (exporter off by default), Sentry (DSN optional).
- Dockerfiles: multi-stage, non-root, slim; targets `api`, `worker`, `test`; `uv sync --frozen`.
- `compose.yaml`: postgres:18 (init script creating roles `app_owner`, `app_user`, `app_scanner`, `auth_owner`, schemas, extensions, SCRAM), valkey:9, rustfs + `storage-init` (boto3 script: buckets, CORS, versioning), mailpit, gotenberg:8 (hardened flags), migrate (one-shot), api, worker, auth (placeholder). Healthchecks with `depends_on: service_healthy` / `service_completed_successfully`. `compose.test.yaml` with tmpfs Postgres, `api-tests` and `e2e-tests` services. `compose.override.example.yaml`.
- Makefile: `up`, `down`, `test`, `e2e`, `test-all`, `lint`, `typecheck`, `migrate`, `openapi`, `client`, `fmt`.
- Pre-commit: ruff, mypy, gitleaks, prettier/eslint.
- CI (GitHub Actions, SHA-pinned): lint → typecheck → unit → Compose integration → OpenAPI/oasdiff → client-diff → image build → Trivy/osv-scanner/pip-audit → (main) publish images. Renovate/Dependabot with a security fast lane for Next/React/Better Auth.
- `infra/`: OpenTofu skeleton for staging + prod (network, Postgres, Valkey, buckets, secrets manager, container service, DNS, TLS); staging deployed from `main` automatically.

**Acceptance**: `make test` green with smoke tests; CI green on a PR; staging serves `/health/ready`; image scan has zero critical findings.
**Docs**: CLAUDE.md, ADR-0001/0002/0005, README quick-start, `.env.example`, `SECURITY.md`, `CONTRIBUTING.md`, PR template.

### M1 · Identity, tenancy & platform core
**Auth service (`apps/auth`)**
- Better Auth 1.7.x on Hono. Plugins: email/password (verification required, reset), **Google**, organization (with `organizationHooks.afterCreateOrganization`, invitations), twoFactor (TOTP + backup codes), jwt (`definePayload`: `sub`, `email`, `name`, `org_id`, `org_role`, `perms_version`, `mfa_enrolled`, `mfa_at` via custom session field; explicit `iss`/`aud`), bearer.
- Microsoft, passkey and magic link move to W-phase/R2. Apple and phone OTP are deferred until mobile (P2).
- Configure `baseURL`, `trustedOrigins`, secure cookies and rate limiting.
- `auth` schema pre-created and owned by `auth_owner`; migrations via `npx auth@<pinned> migrate` as a one-shot Compose service.

**API core**
- JWKS verification (cached, refetch on unknown `kid`, check `iss`, `aud`, `exp`, `nbf`, algorithm allow-list).
- `current_principal`; membership mirror table updated by org hooks via the internal endpoint (signed JWT, `aud=internal`) with a ≤60 s cache; lazy provisioning fallback.
- Tenant context: `SET LOCAL app.tenant_id` per transaction.
- Tenants, branches, user profiles; permission registry; default roles (owner/admin/broker/accounts/csr/viewer) with role→permission mapping owned by the API; `require_permission`; MFA-required policy for `owner` and `accounts` (403 `mfa_required` if not enrolled).
- **RLS framework**: base mixin (`tenant_id`, audit columns, `version`), policy helper, composite-FK helper, **catalog guard test**.
- Audit log (append-only grants); idempotency (Postgres, same transaction); outbox/event bus over Procrastinate; failed-jobs table plus admin-only replay endpoints.
- Optimistic concurrency (`If-Match` / `version`); cursor pagination; rate limiter (Valkey).
- Org settings: profile, timezone, locale, currency, fiscal year, quiet hours.
- Numbering schemes (pattern validation, gapless allocation at issue, per branch/type/period) plus `payment_reference` generator (≤12 alphanumerics, unambiguous charset, check digit).
- Currency table (ISO 4217 minor units); `Money` type.

**Acceptance**
- E2E in Compose: sign up → verify email via the Mailpit API → create org → tenant provisioned (hook path and lazy path both tested) → `GET /api/v1/me` returns permissions.
- Tenancy suite green.
- 50-way numbering concurrency test green.
- Idempotency race test green.
- Membership removal blocks access within 60 s.

**Docs**: ADR-0003/0004/0006/0007/0010/0011; tenancy and auth architecture docs; runbook "rotate JWKS / service keys".

### M2 · Platform services: documents, PDFs, templates, email, public links
**Scope**
- **Documents**: presigned PUT (≤10 min, content-type and size bound, extension + MIME sniff on finalize); presigned GET after a permission check; SHA‑256 hash; versions; entity links; expiry dates.
- **PDF pipeline**: Pydantic view model → Jinja2 (`autoescape=True`, `StrictUndefined`, no tenant-authored templates) → Gotenberg → S3 (hash) → `Document`, cached per document version.
- **Template system**: manifest schema, design tokens, self-hosted fonts, `@page` rules, header/footer; **3 launch templates** (1 free, 2 premium) for quote, invoice, receipt and credit note; tenant branding settings.
- **Public links**: 32-byte tokens with SHA‑256 at rest; scopes `view`/`accept`/`pay`; expiry; revoke; `/api/v1/public/*` routes with per-IP rate limits; HTML rendered for a sandboxed iframe with strict CSP; view counted only on beacon; bot-UA filtering; link events.
- **Email**: adapter (SMTP → Mailpit; SES in prod) with per-tenant From/Reply-To on the shared domain (custom domains in R3); message templates (email) per event and locale; `List-Unsubscribe` + one-click headers on reminder streams; outbound message log.
- In-app notifications (bell) with per-user preferences.

**Acceptance**
- Every template renders with all fixture sets (snapshot + PDF text assertions + visual diff).
- XSS test: tenant fields containing `<script>` and `"><img onerror>` are escaped in HTML and PDF.
- SSRF test: a template referencing `http://169.254.169.254` and internal hosts produces no fetch (Gotenberg deny).
- Presigned URL expiry is enforced.
- Link revocation takes effect immediately.

**Docs**: ADR-0014; template authoring guide; runbook "PDF rendering backlog".

### W1 · Web foundation (starts once M1's OpenAPI is stable)
- Next 16.3:
  - `proxy.ts` handles redirects only;
  - BFF: server components and route handlers obtain the JWT from the auth service (cached per session) and call the API via the orval client;
  - the browser never holds the API JWT;
  - static rewrites `/api/auth/*` → auth service.
- shadcn v4 setup, design tokens, light/dark theme, sidebar + mobile Sheet, ⌘K skeleton, problem+json → toast/field-error mapping, `Idempotency-Key` helper for mutations, next-intl (en), `Intl.NumberFormat` by record currency.
- Screens: sign in/up, verify, 2FA enrol/challenge, org creation, invite acceptance, onboarding wizard shell, organization settings, users & roles, numbering, branding (template picker with live preview).
- Playwright harness in Compose with axe checks; Vitest + MSW.

**Acceptance**: the UI golden path "sign up → org → onboarding → branding" passes Playwright and axe with no serious violations, on desktop and 390 px mobile.

---

## 6. R1 — Invoicing tier

### M3 · Invoicing core (generic pack)
**Scope**
- **Calc engine v1 (`app/calc`)**: line math (qty × price − discount), tax codes (inclusive/exclusive, exempt, zero-rated), per-line vs per-document rounding from the pack, document totals, payment allocation math, currency minor units.
- **Jurisdiction packs v1**: YAML schema (JSON Schema validated), loader to effective-dated DB tables at migration/startup, **`generic`** pack (configurable VAT), pack versioning and sign-off metadata.
- **Clients & contacts**: individual/corporate, E.164 phones, emails, consent timestamps, tags, assigned user, PII encryption (`key_id`, HMAC lookup), duplicate detection (hash/email/phone/PIN), FTS + trigram search, soft delete.
- Item/product catalogue for generic lines.
- **Generic quotes**: lines, sections, optional items, versions (`superseded`), validity, acceptance capture (name, contact, timestamp, IP, UA, terms checkbox), convert to invoice.
- **Billing documents**: invoice and credit note with orthogonal status fields, issue (numbering + `payment_reference` + immutability trigger + ledger journal), void rules, instalment schedules, FX rate at issue, due dates, overdue derived in the tenant timezone.
- **Payments (manual)**: cash/bank/cheque/M‑Pesa reference; allocations many-to-many; unallocated → client credit; refunds linked to credit notes; receipts (numbered, PDF, emailed).
- **Ledger**: chart of accounts v1 (receivable, cash/bank, unallocated cash, tax payable, revenue, client credit); balanced journals per currency; DB-level balance check.
- Client CSV/XLSX import (mapping, dry run, error file, 10k rows within budget).
- Reminder rules v1 (email only): invoice due/overdue, quote expiring; dedupe keys; quiet hours; tenant timezone.
- Tasks (basic).
- Dashboard v1 endpoints (outstanding, overdue, quotes awaiting).

**Acceptance**
- Ledger balance property holds over randomized operation sequences.
- Partial, over- and multi-invoice payment allocation tests pass.
- Time-travel reminder tests across timezones and quiet hours pass.
- 10k-row import passes within budget.
- Contract tests: no 5xx.

**Docs**: ADR-0008/0009/0012/0013; module READMEs; `docs/jurisdictions/generic.md`.

### M4 · Online payments & SaaS billing
**Scope**
- **Payment connections** (per tenant, encrypted credentials, health check, kill switch).
- **`paystack`**: initialize a transaction from the public link (card / M‑Pesa / Airtel / Pesalink), verify-transaction call before marking paid, webhook `/webhooks/paystack/{connection_id}` (HMAC‑SHA512 with the tenant secret, IP allowlist), refunds.
- **Webhook ingress framework**: verify → `webhook_events` (unique provider + event id, tenant id) → 200 → job → domain change + ledger → admin replay.
- Pay-from-link flow on the public page (`pay` scope).
- **SaaS subscriptions**: plans and entitlements (feature flags, seats, document quotas, template tier, storage); `require_feature`, quota checks, usage counters. Trial per D8 (recommend 30-day no-card trial or free capped tier). **`paystack_billing`** (card subscriptions, dunning); M‑Pesa renewal flow (invoice + STK/Paystack charge link + grace period); proration on upgrade; our own subscription invoices (eTIMS via M5).
- `stripe_connect` / `stripe_billing` only if D1 = foreign entity.
- Platform admin API v1 (no UI): tenants, plans, failed jobs, webhook replay. Separate admin auth realm with mandatory 2FA; every tenant-data access audited.

**Acceptance**
- Fake-provider golden path: link → intent → webhook → allocation → receipt → ledger.
- Paystack sandbox smoke tests (`@pytest.mark.sandbox`).
- Duplicate and out-of-order webhooks processed once.
- Forged signature rejected.
- Entitlement and quota enforcement tests.
- **Review checklist confirms no platform-held funds path.**

**Docs**: ADR-0015/0016; runbooks "payment provider outage", "webhook replay"; tenant help article "Connect Paystack".

### M5 · Kenya compliance for invoicing: KE pack + eTIMS + M‑Pesa direct
**Scope**
- **`ke` pack v1 (invoicing subset)**: KES, rounding per line, VAT 16% / exempt / zero-rated codes, eTIMS-required flag for all business tenants, numbering constraints, required fields (KRA PIN). Values carry a source and a sign-off record (D4).
- **Tax adapter**:
  - `manual_reference` stopgap: the tenant records the eTIMS CU invoice number and QR, with validation and printing on the PDF.
  - **`kra_etims_oscu`**: device initialisation per tenant PIN/branch, item and code sync, invoice and credit-note submission, status, retries, offline queue, control number/QR/signature stored and printed. Built and tested against the **KRA sandbox**; production-enabled only after certification.
  - Transitions: an eTIMS-transmitted document can only be corrected by credit note.
- **`mpesa_daraja` (advanced)**:
  - Per-tenant config (paybill/till, `party_b`, passkey, keys, initiator credential); OAuth token cache per tenant.
  - STK Push with `payment_reference` as `AccountReference`.
  - Unguessable per-request callback path; Safaricom IP allowlist (configurable); match + **STK Query confirmation** before marking paid; idempotency on receipt number.
  - C2B register URLs, confirmation handling, **unmatched-payments queue** with fuzzy suggestions, daily Pull/Transaction Status reconciliation job.
  - Per-phone and per-tenant throttles.
  - Guided go-live checklist in onboarding.
- Our own SaaS billing issues eTIMS invoices (we are a tenant of our own tax adapter).

**Acceptance**
- eTIMS sandbox: issue, credit note, offline retry and QR printed — all pass.
- Daraja sandbox:
  - STK success, cancel (1032) and timeout (1037) paths;
  - forged callback (unknown CheckoutRequestID, wrong amount) is rejected;
  - a callback without query confirmation never marks paid;
  - C2B with a mistyped reference lands in the unmatched queue.
- Accountant has signed the KE invoicing values.

**Docs**: ADR-0017; `docs/jurisdictions/ke.md` (invoicing part); runbooks "eTIMS outage/backlog", "M‑Pesa reconciliation".

### W2 / W3 · Invoicing UI
- **W2** (after M3):
  - Clients: list with filters/search/saved filters/bulk actions; 360° timeline; create/edit sheet.
  - Item catalogue.
  - Quote builder (sections, optional items, live totals).
  - Invoice and credit-note editors; issue dialog; send dialog (email + copy link).
  - **Public document page** `/d/[token]`: sandboxed iframe, Accept/Decline, Download, low-bandwidth budget (<150 KB JS on first load, works on 3G).
  - Payments recording and allocation UI; receipts; reminders settings; dashboard v1; tasks; client import wizard.
- **W3** (after M4/M5): pay on the public page (Paystack checkout, M‑Pesa phone prompt with status polling); payment connections settings; eTIMS settings and manual-reference capture; unmatched-payments queue; plan/billing pages; onboarding wizard complete.
- **Acceptance**: the Playwright R1 golden path passes — sign up → onboarding → client → quote → send → (public) accept → convert to invoice → issue (eTIMS fake) → pay (fake provider) → receipt email in Mailpit → dashboard reflects it. Axe passes on all R1 screens. Mobile layouts verified.

### R1 release gate
- [ ] All M0–M5, W1–W3 DoD met; CI and nightly suites green for 7 consecutive days.
- [ ] Load test: p95 < 300 ms on core list/get with a seeded large tenant; PDF generation ≥ target per minute.
- [ ] Security: ASVS L2 checklist for in-scope areas, ZAP baseline clean, dependency and image scans clean, external pen test of auth, public links and webhooks (recommended before paid launch).
- [ ] Ops: backups + PITR enabled and **restore drill performed and timed**; alerting on SLOs (availability 99.9%, webhook-processing lag, job failures, eTIMS submission failures); status page; on-call rota; incident runbook.
- [ ] Compliance: ODPC registration filed; privacy policy, terms, processor agreement, cookie notice published; DSR export/erasure (anonymisation) endpoints working; retention jobs scheduled.
- [ ] eTIMS: certified integrator, **or** the `manual_reference` stopgap explicitly approved by the tax adviser for pilot use.
- [ ] Pilot onboarding done; feedback loop (in-app + WhatsApp) established.

---

## 7. R2 — Broker MVP

### M6 · Insurance master data
- **Insurers**: directory, regulator number, contacts, remittance bank/paybill details, `remittance_method` (gross / net of commission), default collection mode, logo.
- **Classes of business**: global defaults + tenant custom (split RLS). Each has a **risk JSON Schema** (motor, medical members, property, marine, WIBA, travel) and a business line (general/long-term).
- **Products**: rating basis (rate on sum insured, flat, per-member tiers, manual), min premium, benefits/extensions, excess text, wordings (documents), insurer short-period table.
- **Commission rate tables**: insurer × class × product, new/renewal, effective-dated, tiered.
- Tenant `intermediary_type` (broker / agent / non-resident) → WHT rate selection.
- Imports: insurers, products, commission tables.
- **Acceptance**: effective-dating tests (boundary dates, overlaps rejected); risk-schema validation tests; RLS for mixed global/tenant classes.

### M7 · Premium engine & insurance quotes
**Calc engine v2**
- Rating bases.
- Benefits and loadings/discounts per accountant-approved definitions.
- Min premium (applied once, at the defined point).
- **KE levies**: training levy 0.2% general-only; PCF 0.25% client-charged on all eligible classes.
- **Stamp duty rule types**: flat KES 40; life per 10,000; marine bands; cover-note exemption.
- Fees with a tax code that can carry excise (pending D4).
- `charged_to` filter: insurer-borne levies never reach the client.
- Fully explained `premium_breakdown` (rule ID, version, rounding).

**Insurance quotes**
- Multiple options (insurer + product), risk details per schema, side-by-side comparison view model, commission computed but never in client-facing view models (enforced by a separate schema plus a test).
- Accept a selected option.
- Versions and supersede.

**Golden scenarios**: ≥40 signed by the accountant (D4), stored as YAML, run on every PR.

**Acceptance**
- Golden suite passes.
- Hypothesis properties pass.
- Commission absent from public HTML/PDF (test greps the rendered output).
- Quote comparison template renders 2–5 options.

### M8 · Policies, debit notes & premium handling (s.156-aware)
- **Quote → policy conversion**: policy `pending`; `policy_number` nullable until bound; risks; premium breakdown snapshot; commission-rate snapshot; payment plan.
- **Debit note** (client-facing premium bill, **not eTIMS**) with instalments and `payment_reference`.
- **Collection modes**:
  - `broker_collects`: payment into the broker's premium collection account → **premium trust ledger account**.
  - `insurer_direct`: client pays the insurer; the broker records the insurer's confirmation.
- **Activation gating**: `pending → active` requires premium-received evidence or an r.43 exception record (medical instalments, declaration 75%, WIBA/CIT provisional, marine 15 days, bonds/CAR). Cover notes are supported.
- Policy states with an explicit transition table; expiry/lapse jobs in the tenant timezone.
- **Renewals**: generate a renewal quote N days before expiry; expiring vs renewing comparison; renewal pipeline endpoints.
- Reminder rules v2 (email): renewal offsets, instalment due, document expiry (KYC, licence).
- KYC documents with expiry tracking.
- **Acceptance**: a policy cannot activate without evidence (tests per r.43 exception); trust-account journals balance; renewal generation is idempotent; ledger reconciles with document totals.

### M9 · Commissions & remittances
- **Commission entries**: gross → **WHT withheld by insurer** (5/10/20% by intermediary type) → net expected. VAT on commission is pack-driven (KE: exempt). Clawback on refunds. States expected → invoiced → received → paid_out.
- **Commission/fee invoice to insurer**: a new document type, **eTIMS-transmitted (exempt-coded)**, numbered, PDF.
- WHT certificate capture and reconciliation (certificate number, amount; difference report).
- Agent/sub-agent splits (percent/fixed, multi-level; base per tenant setting, default net); splits ≤ base enforced.
- **Remittances**: batch builder from paid debit notes (gross or net per insurer), remittance advice PDF, record payment to insurer, mark remitted.
- **Ageing**: outstanding premium per insurer with **>60-day flag**; INS 153‑1-style half-yearly outstanding-premium report; 31‑Dec premiums-due statement; aged debtors/creditors.
- **Acceptance**: the E2E broker golden path — quote with 2 options → send → accept → convert → debit note → pay (fake) → policy activates → commission expected (WHT computed) → commission invoice (eTIMS fake) → remittance batch → reports reconcile with the ledger.

### W4 / W5 · Broker UI
- **W4**: insurers/products/classes/commission-table settings; quote builder with live premium calculation and the option comparison view; public comparison page with option selection; policy list and detail (risks, documents, billing, commission); conversion wizard; activation evidence capture; renewals board.
- **W5**: commissions list, WHT certificates, commission invoices; remittance batch builder and advice; ageing and regulatory reports with CSV/XLSX export; dashboard v2 (written, collected vs outstanding, commission earned vs received, renewals due).
- **Acceptance**: the Playwright broker golden path passes; axe passes.

### R2 release gate
- R1 gate items re-verified.
- **Lawyer opinion (D5) received and reflected** (collection modes, positioning, e-acceptance wording).
- **Accountant sign-off on the full KE pack and golden suite.**
- 3–5 broker pilots live.
- Restore drill repeated.
- Pen-test findings closed.

---

## 8. R3 — Broker Pro & GA hardening

### M10 · Endorsements & cancellations
- Endorsement types (add/remove risk, change sum insured/cover).
- Pro-rata (`remaining_days / period_days`, leap-year tests) and insurer short-period tables.
- Levies recalculated per pack, with non-refundable levy flags.
- Debit or credit note; commission adjustment and clawback; cancellations with refund and credit note; refund through the payment adapter where supported.

### M11 · Reconciliation, messaging channels & imports
- **Insurer statement import**: CSV/XLSX (PDF later with AI); column mapping saved per insurer; auto-match on policy number + amount + date; fuzzy suggestion queue; accept/dispute/adjust; variance report.
- **SMS** (Africa's Talking; platform transactional sender ID by default, tenant sender IDs on request; DLR callbacks via secret path; STOP handling and global suppression).
- **WhatsApp Cloud** (Tech Provider + Embedded Signup; approved template names; `X-Hub-Signature-256`; per-message cost logging).
- Channel fallback rules.
- Per-tenant custom email domains (DKIM/DMARC verification).
- **Imports**: policies and opening balances (book of business) with dry run and error file.
- Custom roles (Broker Pro) on the API permission registry.
- Microsoft and passkey sign-in.

### M12 · Reports, data rights & hardening
- Full reports: production by insurer/class/broker/branch/period; premiums issued, collected and remitted; renewal retention and lapse rate; quote conversion; commission statements. All reconcile to the ledger in tests.
- **Full tenant export** (async ZIP of CSVs + documents).
- **Data-subject requests**: export, rectify, erase as anonymisation where financial retention applies.
- Retention schedule jobs.
- Breach-logging workflow.
- Performance: 50k-policy tenant, p95 < 300 ms; query plans reviewed (`tenant_id`-leading indexes).
- Final ASVS L2 audit; external pen test; chaos drills (provider outage, Valkey loss, Postgres failover); DR test (RPO ≤ 15 min, RTO ≤ 4 h).

### W6 · Pro UI
Endorsement wizard; reconciliation workspace (upload → mapping → match queue); message-template and channel settings; WhatsApp onboarding; import wizards; reports with charts and filters; audit-log viewer; data export.

### GA gate
All prior gates plus:
- SLOs met for 30 days.
- On-call rota and runbooks exercised.
- Documentation complete for every module.
- Help centre covers all core flows.

---

## 9. Later backlog (P2/P3, re-prioritise after R2 pilot feedback)
- **Leads**: pipeline, web forms/landing pages under tenant brand, API keys.
- **Claims**: registration, checklist, insurer correspondence.
- **Client portal**: magic link/OTP, policies, documents, payments, service requests.
- Recurring invoices.
- Duplicate merge.
- **Admin console UI**: impersonation, audited and time-boxed.
- **Expo mobile app** (SDK 57+, Apple/phone OTP sign-in at that point).
- M‑Pesa Ratiba instalments.
- AI extraction of insurer schedules (Claude API; human review; per-field confidence; metered, with a tenant off-switch).
- Renewal-risk scoring.
- Facultative reinsurance.
- SSO/SAML.
- Custom portal domains.
- Public API and tenant webhooks.
- Regulator returns automation.
- UG/TZ/RW packs (values to verify: UG training levy 0.5%, UG stamp duty UGX 35,000, VAT on UG non-life premium; TZ premium levy 1.5%).

---

## 10. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| KRA integrator certification slow or blocked | M | High (R1 in KE) | Start week 1; `manual_reference` stopgap approved by tax adviser; generic-pack markets unaffected |
| Regulatory values wrong in production | M | High | Packs as signed data; golden suite; CODEOWNERS on packs; effective-dated changes without deploys |
| s.156 legal position changes (appeal / new regs) | L‑M | High | Collection mode switchable per policy/insurer; lawyer review per release |
| Payment provider incident or credential leak | M | High | Per-tenant encrypted credentials, kill switch per integration, confirmation before marking paid, reconciliation jobs |
| Cross-tenant data leak | L | Critical | RLS + composite FKs + guard test + generated tenancy suite + pen test |
| Next/Better Auth critical CVEs | H (historically frequent) | High | Pinned versions, security fast lane, auth enforced in FastAPI regardless of frontend |
| Scope creep delays revenue | H | High | Release gates; P2/P3 backlog frozen until R2 feedback |
| Small Kenyan broker TAM; InsurOps competition | M | Medium | Invoicing-led funnel, KES/M‑Pesa pricing, compliance moat, East Africa packs |
| AI-agent-generated code quality drift | M | Medium | DoD checklist, import-linter, mandatory reviews, CODEOWNERS on critical paths, small PRs |

---

## 11. Immediate next steps (first 10 working days)

1. Product owner reviews SPEC_REVIEW and decides **D1, D2, D6, D7** (D3, D11 by tech lead).
2. Start the long-lead items in §4 (eTIMS certification, ODPC, Paystack, Daraja, SES, Meta).
3. Engage the tax adviser and lawyer; begin the golden-example workbook.
4. Amend `PROJECT_SPEC.md` with the corrections in SPEC_REVIEW and move it to `docs/PROJECT_SPEC.md` (one PR, reviewed). Write CLAUDE.md.
5. Execute **M0** and open ADR-0001…0006.
6. Design kicks off brand, the 3 templates and the onboarding, quote-builder and public-page wireframes.
