# Changelog

All notable changes are recorded here ([Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
commits follow Conventional Commits).

## [Unreleased]

### Added: R2.5 plans and subscriptions (2026-10-09)
- **Plans**: Free, Agent, Agency and Business, with the approved prices (docs/PRICING.md, ADR-0025).
  - Every new account gets a 30-day Agency trial; existing accounts get one from today.
  - After the trial an account moves to Free unless it pays.
- **Settings → Plan & billing**:
  - current plan, usage meters (clients, documents this month, seats);
  - plan cards with monthly or yearly prices (2 months free) and the founding price (50% off for 12 months,
    first 100 accounts);
  - pay by M-Pesa prompt to the platform's Paybill, followed live; payment history with receipts.
- **Plan rules enforced by the API** (402 problem+json):
  - features: `plan_feature` for quotes, policies and renewals (not in Business), commission, Excel/CSV
    import, comparison quotes, client reminder emails, branding and eTIMS;
  - limits: `plan_limit` for Free's 50 clients and 10 issued documents a month, and for team seats (checked
    before invitations are sent or accepted).
- **Lapsed plans**: 7 days of grace, then read-only (reading, downloads and paying still work), with a
  banner on every page. A banner also appears in the last 7 days of the trial.
- Navigation hides what the plan does not include; opening such a page explains how to unlock it.
- New settings: `PLATFORM_MPESA_*`.

### Added: R2.4 optional eTIMS (2026-10-09)
- Settings → **Tax & eTIMS**: off by default.
- When it is on, issued invoices and credit notes have a KRA eTIMS panel to record the CU invoice number and
  the verification link from the business's own eTIMS tool. They are printed on the PDF and on the client's
  page.
- Documents still missing a number are flagged in the list and on the invoicing overview.

### Added: R2.3 M-Pesa Daraja (2026-10-08)
- **Settings → Payments:**
  - connect the business's own Paybill or Till (Daraja keys checked with Safaricom and stored encrypted);
  - register Paybill payments; turn off;
  - card payments shown as **coming soon**.
- **M-Pesa payment prompts:**
  - from the invoice page ("Ask for M-Pesa payment"), and by the client from the invoice link ("Pay with
    M-Pesa");
  - followed live until paid, cancelled or timed out;
  - recorded only after Safaricom confirms (STK Query); whole shillings, with any excess kept as credit.
- **Paybill payments made by hand:**
  - matched to invoices by payment reference;
  - otherwise queued under Payments → "M-Pesa payments to match", to assign to a client or set aside.
- Callbacks are stored before processing (duplicates ignored) on a secret path per connection, with an
  optional IP allow-list (`MPESA_CALLBACK_ALLOWED_IPS`).
- A simulator for trying it out without Safaricom (not available in production).
- A sandbox smoke test runs in CI with repo secrets.
- Runbook: `docs/runbooks/mpesa-go-live.md`.

### Added
- Book import accepts **Excel (.xlsx)** files as well as CSV. Dates, numbers and yes/no cells are read as
  typed; old `.xls` files get a hint to resave.
- Pricing approved (docs/PRICING.md); payment, eTIMS and hosting decisions recorded (ADR-0015, ADR-0017,
  ADR-0020).

### Added: R2.2 Sales quotes, reminders, invoicing dashboard (2026-10-08)
- **Sales quotes:**
  - section headings and optional extras;
  - sending issues the quote with a link where the client ticks the extras they want and accepts, or
    declines;
  - "Create invoice" turns an accepted quote into a draft invoice with the chosen extras;
  - expiry is derived from the validity date.
- **Reminder emails to clients** (off until the business turns them on): before invoices fall due, after they
  are overdue (default 1, 7 and 14 days) and before quotes expire, each sent once.
- **Invoicing overview:** what clients owe, overdue amount, ageing, collected this month, quotes awaiting an
  answer.
- Document templates show section headings and an "Optional extras" table (template version 3).

### Added: R2.1 Invoicing core (2026-10-08)
- **Item catalogue** (Settings → Items & prices) with default price and tax code.
- **Invoices and credit notes:**
  - drafts with catalogue or free-text lines, discounts, prices with or without VAT; VAT per line from the
    jurisdiction pack;
  - issue: gapless number, M-Pesa payment reference, frozen by a database trigger;
  - credit notes against an invoice (never more than its total), voids;
  - PDF, tracked link, email and WhatsApp share.
- **Payments received:**
  - applied to invoices oldest first or as chosen; excess kept as client credit and usable later;
  - voids reverse everything a payment paid; numbered receipt PDFs;
  - client account (owes you / credit on account), payments list.
- **Double-entry ledger (ADR-0012):** each entry's balance is enforced at commit, and the journal is
  append-only. Tested with random operation sequences.
- ADR-0009 (document states) and plan amendment A1.2 (R2 slices).
- Permissions `invoice:write`, `invoice:issue`, `payment:write`, `catalog:manage`.

### Changed
- CI runs the end-to-end suites on pull requests. `main` is protected: every CI job must pass and history
  stays linear.
- The jurisdiction pack endpoint lists tax codes.
- A test fails when two modules export the same schema name, which would break the generated web client.

### Security
- Runtime images apply Debian security updates and no longer ship package managers: npm, corepack and yarn
  are gone from the web and auth images, and the system pip from the API image. The CI Trivy scan is clean.

### Added: R1.5 Commission, book import, dashboard v2 (2026-10-08)
- **Commission tracking:**
  - expected commission on each policy (from the quote, the product's rate, or set by hand);
  - commission received recorded per insurer receipt and split across policies, with WHT at the pack rate
    (10% for resident agents) or the insurer's figure, and the KRA WHT certificate number;
  - receipts are voided, never deleted;
  - statement of expected, received and owed; yearly summary by month and insurer; WHT certificates list.
  - New page **Commission**, shown only to members who can see commission. New permission
    `commission:manage` (owners, admins, accounts).
- **Import the book from a spreadsheet (CSV):**
  - column detection from agents' own headings;
  - Kenyan date and amount formats, class matching;
  - client matching by phone, email, PIN or ID; duplicate policies skipped;
  - preview of every row, then a single-transaction import with an import log;
  - imported policies are active (basis `imported`, ADR-0019).
- **Dashboard v2:** this year's premium written, premium still owed, commission expected vs received,
  renewal retention and premium by month.
- `app/calc/commission.py`: commission and WHT arithmetic shared by quotes, policies and receipts.

### Fixed
- Activation evidence recorded the agency's intermediary type and timezone instead of the pack version.
- Renewal quotes now use the product's renewal commission rate.

### Added: R1.4 Policy book & renewals (2026-10-08)
- **Policies** from an accepted quote (or "accepted by phone": the agent picks the option) or entered by hand:
  - insurer's policy number, what is covered, cover dates, premium, breakdown and expected commission;
  - client tab, list with search and filters, policy page.
- **No premium, no cover** (ADR-0019): a policy activates only when the insurer confirms cover and either the
  premium is paid in full or a Regs r.43 exception from the jurisdiction pack applies. The KE pack gains
  `premium_exceptions`, pending sign-off.
- **Premium payments, recorded, never held:**
  - void with a reason, never deleted;
  - premium the agent collects opens a same-day "remit to the insurer" task (Regs r.42), closed when it is
    marked as remitted;
  - new permission `premium:write` (agents, accounts, owners and admins; not assistants).
- **Renewal board:**
  - stages: to contact, contacted, quoted, renewed, lost (with a reason);
  - WhatsApp click-to-chat and email reminders, logged on the client timeline;
  - renewal quote prefilled from the policy; "record renewal" for cover renewed elsewhere.
- **Daily renewal reminders** at the agency's offsets (default 30/14/7 days): owner notified, client emailed
  only if the agency turns it on. Settings on the board.
- **Dashboard:** renewals due in 30 days, premiums to pass on, active policies.
- Migration 0007: `policies`, `policy_payments` and `renewal_reminders` (RLS forced, no deletes); tenant
  reminder settings; the cross-tenant scan as a SECURITY DEFINER function.

### Added — R1.3 Insurance quotes (2026-10-08)
- **Quotes** for clients with up to 8 insurer options, cheapest first. Each option freezes the calculation
  (breakdown, pack version, sources); commission stays internal.
- **Send:**
  - quote number;
  - branded comparison PDF (the templates gain an options table);
  - tracked link with view and accept;
  - email to the client, a WhatsApp share link, and the lead moved to "quoted".
- **Client page** `/d/[token]`: view the quotation (sandboxed), download the PDF, accept an option (name,
  phone, terms) or decline. A view is counted by beacon, and acceptance evidence is recorded.
- **Agent screens:** quotes list, new quote from a client, quote page (options, commission, send dialog,
  withdraw, PDF, client response).
- **Per-agency switch** for multi-insurer quotes (pending legal opinion D5).
- **Tests prove commission never appears** in the public JSON, HTML or PDF; there is a Playwright journey from
  agent to client acceptance.

### Fixed
- `proxy.ts` no longer redirects the anonymous `/public-api/*` calls to sign-in.
- Validation errors raised inside services return 422 problems instead of 500s.

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
