# Changelog

All notable changes are recorded here ([Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
commits follow Conventional Commits).

## [Unreleased]

### Added — R1.2 Insurers, premium engine and Kenya pack (2026-10-08)
- **Jurisdiction packs** (ADR-0013): versioned YAML, validated on load.
  - `ke` 2026.1, **pending adviser sign-off**: training levy 0.2% (general), PCF 0.25% (client) plus the
    insurer-borne 0.25%, stamp duty KES 40 / life KES 7.50 per 10,000 / marine and travel entered manually,
    premium and commission VAT-exempt, WHT 10% agent / 5% broker / 20% non-resident, excise 20% on fees
    (pending confirmation), 24 classes of business.
  - `generic` 2026.1.
- **Premium engine** (`app/calc`, pure):
  - rating bases, minimum premium, benefits, loadings and discounts;
  - levies by business line, class and document kind, effective dates;
  - stamp-duty rule types; fees with tax; commission (gross, WHT, net);
  - every line cites its rule and legal source;
  - 14 hand-calculated golden scenarios and property tests.
- **Insurers and products:** each agency's appointments, rates, member tiers, benefits, excess wording and
  commission rates.
- **Premium calculator and multi-insurer comparison:** API and screen, cheapest first, with a breakdown and the
  agent's commission. Commission is hidden from assistants and viewers.
- **Web:** Settings → Insurers & products; Premium calculator; a sign-off banner wherever statutory amounts
  appear.
- **Money and rates reject JSON numbers** (strings only), enforced by shared `NoFloat` types.

### Added — R1.1 Agent CRM: clients, leads, tasks (2026-10-08)
- **Clients and households:**
  - individual and corporate clients with phones normalised to E.164;
  - KRA PIN, encrypted ID and passport numbers (AES-GCM with a keyed lookup hash, ADR-0018) and an audited
    reveal;
  - tags, consent, households, corporate contacts;
  - activity log (calls, WhatsApp, meetings, notes) and a 360° timeline merging activities, documents, tasks,
    emails and changes.
- **Search** by name (trigram), phone in any format, email, KRA PIN or ID number.
- **Duplicate detection** on phone, email, PIN or ID, with a live warning in the form. Matches in another
  agent's book are counted, not shown.
- **Agent scoping:** agents see and own their own clients, leads and tasks; owners, admins and assistants see
  the whole agency.
- **Leads:** pipeline (new, contacted, quoted, won, lost) with estimated premium per stage, follow-ups,
  conversion to a client, lost reasons, and a notification on assignment.
- **Tasks:** linked to records; overdue, today and upcoming in the agency's timezone; one-time due reminders
  through a narrow cross-tenant scan.
- **Dashboard:** overdue and today's tasks, follow-ups due, new clients, documents expiring, pipeline.
- **Web:**
  - clients list with search and an add sheet with live duplicate check;
  - client 360° page (call, WhatsApp, email; timeline; documents with expiry; tasks);
  - leads board (columns on desktop, stage tabs on phones);
  - tasks page;
  - dashboard home.
- **Tests:** integration (encryption at rest, duplicates, scoping, search, timeline, pipeline, reminders),
  web unit tests, and a Playwright journey from lead to client to task.

### Fixed
- The PDF renderer retries a timed-out render once (Chromium cold starts), not only 5xx errors.
- Tests no longer depend on wall-clock speed: token timestamps are computed at run time, Hypothesis has no
  per-example deadline, rate-limit tests tolerate minute boundaries, readiness is polled, and PDF tests share
  one xdist worker.

### Added — W1 Web foundation (2026-10-07)
- **Web app** (`apps/web`, Next.js 16.3, React 19, Tailwind 4, shadcn/Radix, TanStack Query, next-intl):
  - sign in and sign up with email confirmation, two-step sign-in, password reset, invitation acceptance;
  - onboarding: create agency, then details, then brand, with a live document preview;
  - app shell with sidebar, mobile menu, ⌘K jump menu, notification bell and agency switcher;
  - settings: agency profile, team (invite, change role, remove), documents & brand (template, colours, logo
    upload, footer, payment details, live preview, sample PDF), document numbers (live preview), security
    (optional TOTP with QR code and backup codes).
- **BFF** (ADR-0021): same-origin `/api/auth` proxy and `/bff/api/v1` proxy that attaches the API token
  server-side; the token never reaches the browser.
- **Generated API client** (orval, ADR-0022) with RFC 9457 error mapping, automatic Idempotency-Key and If-Match.
- **Design:** paper, ink, acacia and maize tokens; Bricolage Grotesque and Atkinson Hyperlegible; the agency's
  stamp seal; light and dark themes.
- **Tests:**
  - Vitest and MSW unit and component tests;
  - Playwright golden path in Compose (`make e2e-web`) on desktop and a 390 px phone, with axe WCAG 2.2 AA
    checks.
- **CI:** web checks, generated-client drift, web image scan, browser E2E on `main`.

### Changed
- `BETTER_AUTH_URL` is now the web origin (the web app proxies `/api/auth/*`).
- API schemas renamed for unique names in the contract: `MessageTemplateOut`, `DocumentLinkOut`,
  `NumberingPreviewRequest`/`NumberingPreviewOut`, `TemplatePreviewRequest`.

### Added — M2 Platform services (2026-10-07)
- **Documents** (ADR-0023):
  - presigned uploads with signed size and type;
  - verification on completion (magic bytes vs extension allow-list, size, SHA-256), rejected bytes deleted;
  - versions, links to any entity, expiry dates, archive;
  - presigned downloads after the permission check.
- **PDF and templates** (ADR-0014):
  - sandboxed Jinja2 with autoescape and self-contained HTML (inline fonts and logo, strict CSP);
  - Gotenberg renderer with retry and an allow-list;
  - 3 launch templates: Classic (free), Savanna and Executive (premium);
  - tenant branding: template per document type, colours, font pair, logo, footer, payment instructions;
  - live preview, including unsaved changes;
  - generated PDFs cached per content.
- **Public links:**
  - hashed 32-byte tokens, scopes, expiry, immediate revocation;
  - per-IP rate limits;
  - sandboxed web view;
  - beacon-based view counting with bot filtering;
  - link events;
  - optional emailing on creation;
  - the first view notifies the agent.
- **Email** (ADR-0024):
  - SMTP adapter (Mailpit locally);
  - "Agency via BrokerOS" with the agency's Reply-To;
  - templates per event with tenant overrides;
  - transactional and reminders streams with RFC 8058 one-click unsubscribe and suppression;
  - outbound message log;
  - idempotent send job.
- **In-app notifications** with per-user preferences (in-app and/or email).
- **Tests:**
  - every template × document type rendered to real PDFs and checked with text assertions;
  - fixture sets (long names, 150 lines, UGX, RTL);
  - XSS escaping in HTML and PDF;
  - an SSRF canary on the private network;
  - presigned upload and download enforcement and expiry;
  - SMTP delivery checked through Mailpit.

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
