# Insurance Broker & Agent SaaS — Project Specification and Handover

> **⚠ Amended (2026-10-07).** This spec has been reviewed. Where they conflict, the following take precedence, in order:
> accepted ADRs in `docs/adr/` → `docs/IMPLEMENTATION_PLAN.md` (incl. Amendment A1: **Kenyan insurance agents are the
> target, not brokers**) → `docs/SPEC_REVIEW.md` → this file. Notably superseded here: Kenya levy/tax values (§6.6),
> Stripe as primary provider (§3.7, §3.17), MinIO (§4.3, §10), PG 17 / Python 3.13 / Redis 7 / Celery (§4.3), the RLS
> predicate (§5.2), billing/quote state machines (§6.5), `NUMERIC(20,2)` (§5.2) and "no UI until B8" (§0.2.1).

> Working name: **BrokerOS** (placeholder — replace when branding is decided).
> This document is the single source of truth for the AI coding agents (Claude Code) building this product. Read it fully before writing any code.

---

## 0. Instructions for the coding agents

### 0.1 How to use this document
- Treat this file as the product and engineering spec. Place it at `docs/PROJECT_SPEC.md` and create a short root `CLAUDE.md` that points to it and summarises the working rules in §0.2.
- When a requirement is ambiguous, choose the option most consistent with this spec, then record the decision as an ADR in `docs/adr/NNNN-title.md`, using the Context / Decision / Consequences format.
- Items marked **[VERIFY]** are facts that need confirming against current regulations or vendor docs before they are seeded as data. Never hardcode them in logic.
- Items marked **[DECISION PENDING]** need product-owner input. Implement them behind configuration, with a sensible default.

### 0.2 Working rules
1. **Backend first.** Build and fully test the backend (milestones B0–B8 in §14) before starting the frontend. The frontend starts only once the backend test suite passes inside Docker Compose.
2. **Everything runs in Docker Compose.** Every service, test run and migration must work through `docker compose`. Local-only shortcuts are fine for speed, but CI and the definition of done use Compose.
3. **Work milestone by milestone.** Each milestone ends with green tests, a working migration, an updated OpenAPI spec, updated docs and a short entry in `CHANGELOG.md`.
4. **Never hardcode jurisdiction rules.** Tax rates, levies, withholding tax, numbering formats and statutory fields go in versioned, effective-dated configuration (see §6.6, the "jurisdiction packs").
5. **Money is never a float.** Use `Decimal` in Python and `NUMERIC` in Postgres. Strings in JSON.
6. **Tenant isolation is non-negotiable.** Every tenant-owned table has `tenant_id`, and Postgres Row-Level Security enforces it. Tests must prove one tenant cannot read or write another's data.
7. **Financial records are immutable once issued.** Correct them with void, credit note, reversal or endorsement. Never hard-delete issued financial documents.
8. **Use Conventional Commits** (`feat:`, `fix:`, `chore:` …) and small, focused PRs or commits.
9. **No secrets in the repo.** Maintain `.env.example` with every variable documented.
10. **Ask before adding heavy dependencies** not listed in this spec. Prefer the standard library and the listed stack.

### 0.3 Definition of done (applies to every milestone)
- [ ] Alembic migration(s) created, reviewed, and reversible where practical.
- [ ] Unit tests for domain logic (calculations, state machines, numbering).
- [ ] Integration tests against real Postgres, Redis, MinIO and Mailpit in Compose.
- [ ] RLS and permission tests for every new tenant-scoped endpoint.
- [ ] `ruff check`, `ruff format --check` and `mypy --strict` (or `pyright` strict) pass.
- [ ] Coverage ≥ 85% for `app/modules/**/service.py` and `app/core/**`.
- [ ] The OpenAPI schema is generated and committed (`openapi.json`), with no unintended breaking changes.
- [ ] The full suite passes: `docker compose -f compose.yaml -f compose.test.yaml run --rm api-tests`.
- [ ] Docs updated (module README, ADRs, `.env.example`).

---

## 1. Product overview

### 1.1 Vision
An all-in-one, self-serve, beautifully designed SaaS for **insurance agents, brokers and (later) reinsurance brokers**. It replaces the typical patchwork of agency management system, CRM, client portal, payments tool, invoicing tool and spreadsheets.

It is also sold as a standalone **quotation and invoicing SaaS** for any small business. Users choose from premium templates, send documents as trackable links and PDFs, and get paid online. This tier is both a revenue line and the top of the funnel for the broker suite.

### 1.2 Two product tiers (one codebase, feature-flagged by plan)
| Tier | Audience | Core value |
|---|---|---|
| **Invoicing** (Free / Pro) | Freelancers, SMEs, independent agents | Premium quote and invoice templates, tracking links, online payment, reminders, clients |
| **Broker** (Starter / Pro / Enterprise) | Insurance agents, agencies, brokerages, later reinsurance brokers | Everything in Invoicing plus policies, insurer markets, premium and levy calculation, debit and credit notes, commissions, remittances, reconciliation, renewals, claims, client portal, leads, reports |

### 1.3 Market research summary (context for product decisions)
**Incumbent agency management systems** (Applied Epic, Vertafore AMS360, HawkSoft, EZLynx, QQCatalyst, Momentum/NowCerts):
- Strengths: deep policy and accounting features.
- Weaknesses: dated, click-heavy UX; custom or demo-only pricing; weak or no client-facing experience; US-centric.

**Point tools layered on top**, which agencies pay for in addition to their AMS:
- AgencyZoom: sales pipeline and renewals CRM, from about $149/month. Internal only, with no client login.
- GloveBoxCRM: branded client app, from about $499/month.
- ePayPolicy: premium payment collection.
- Assembly: client portal.

**Regional broker systems** in emerging markets (SAIBA, Simson, TBW, BrokerEdge, and newer local entrants such as InsurOPS in Kenya) are often ERP-style products that require implementation projects rather than self-serve signup.

**Generic invoicing tools** (Zoho Invoice is free, FreshBooks starts at about $23/month, Invoice Ninja is open source, PandaDoc is known for view tracking) set the bar for polish and tracking. None of them understands insurance: insurers, policies, levies, debit notes or commissions.

**Reinsurance platforms** (Bifrost, Relay, Marrikel, WCL/Zywave) are specialist and serve larger markets. We do not compete there early. We start with simple facultative placements.

### 1.4 How we win (differentiators to protect in every design decision)
1. **Insurance-native documents.** Quotes compare several insurers side by side, with a full premium breakdown (basic premium, levies, taxes, fees). One click turns an accepted quote into a policy, a debit note and a reminder schedule.
2. **Excellent send-and-track experience.** Branded public links let the client view, accept, e-sign (simple acceptance first) and pay by mobile money or card. The broker sees live status: sent → viewed → accepted → paid.
3. **Money reconciliation.** Track premium collected from the client, premium remitted to the insurer, and commission expected versus received. Insurer commission statements are imported and auto-matched to policies.
4. **Local compliance as a moat.** Pluggable jurisdiction packs cover tax e-invoicing (for example Kenya's KRA eTIMS), statutory levies, withholding tax and regulator report formats.
5. **Reminders on the channels clients actually read.** WhatsApp and SMS as well as email, with pay links included.
6. **Self-serve onboarding in an afternoon.** Spreadsheet import of the existing book of business, public pricing, no sales call.
7. **AI that saves typing** (Phase 3). Extract policy data from insurer PDF schedules, predict renewals at risk, draft client messages.
8. **Premium template library.** Template design is a real product investment, not decoration.

### 1.5 Launch market
**[DECISION PENDING]** The default assumption is **Kenya / East Africa first**, with the architecture multi-country from day one:
- currencies: KES default, plus USD and others;
- payments: M-Pesa and cards;
- tax: KRA eTIMS;
- levies: per the Kenya jurisdiction pack.

All of this must be configuration, not code paths, so new jurisdictions can be added as data plus adapters.

---

## 2. Users, roles and permissions

### 2.1 Actor types
- **Tenant user**: staff of a brokerage or business. Belongs to one or more organizations (tenants).
- **Client portal user**: a broker's client (individual or corporate contact). Has a limited portal login (magic link or OTP) and only sees their own records.
- **Public link visitor**: anyone holding a valid signed document link. Has no account and is scoped to one document and its allowed actions.
- **Platform admin**: our internal staff, for support and billing. Kept separate from tenant roles, with access to tenant data audited.

### 2.2 Tenant roles (default set; tenants can create custom roles in Broker Pro and above)
| Role | Summary |
|---|---|
| `owner` | Everything, including billing, deleting the organization and transferring ownership |
| `admin` | Everything except billing and ownership transfer |
| `broker` / `agent` | Clients, leads, quotes, policies, claims and tasks they own or are assigned; view own commissions |
| `accounts` | Invoices, receipts, payments, remittances, commissions, reconciliation, financial reports |
| `csr` (service) | Clients, documents, endorsements, claims and tasks; no commission or financial reports |
| `viewer` | Read-only |

Permissions are **fine-grained strings** (for example `quote:create`, `policy:endorse`, `commission:read:all`, `commission:read:own`, `report:financial`). Roles are bundles of permissions. Each API endpoint declares the permission it requires. Record-level scoping ("own" versus "all") is applied in service queries.

---

## 3. Feature specification by module

Phase key: **P1** = MVP, **P2** = second release, **P3** = later.

### 3.1 Tenancy, organization and settings (P1)
- Organization profile:
  - legal name, trading name, registration number, tax PIN or VAT number, regulator licence number and expiry;
  - addresses, logo, brand colours, default currency, timezone, locale, fiscal year start.
- Branches (optional) with their own numbering prefixes and tax device or branch IDs.
- Bank and mobile-money payment instructions printed on documents.
- Document numbering schemes per document type and branch. The format is a pattern such as `INV-{YYYY}-{SEQ:5}`, with yearly or never reset. Numbers are gapless and allocated at issue time, not at draft time.
- Default terms and notes per document type, email signatures, and quiet hours for reminders.
- Jurisdiction pack selection (see §6.6).

### 3.2 Clients, contacts and KYC (P1)
- Client types: **individual** and **corporate**. Corporate clients have multiple contacts with roles (finance, HR, decision-maker).
- Fields:
  - names, ID or passport number (encrypted), tax PIN, date of birth, gender (optional);
  - phones (E.164) and emails, preferred channel (email / SMS / WhatsApp), addresses, occupation or industry;
  - source, tags, assigned broker, notes;
  - marketing consent and communications consent with timestamps.
- KYC documents (ID copy, tax PIN certificate, certificate of incorporation, CR12 or similar) with expiry tracking.
- Client 360° timeline: quotes, policies, invoices, payments, claims, messages, documents, tasks and audit events.
- Duplicate detection on email, phone, ID number and tax PIN, with a merge tool (P2).
- Import from CSV or XLSX with a column-mapping wizard, validation preview and an error report (P1).

### 3.3 Leads and pipeline (P2)
- Lead capture through:
  - embeddable web form and hosted landing page per tenant (with a "get a quote" form per class of business);
  - manual entry and CSV import;
  - an API key for website integrations.
- A Kanban pipeline with configurable stages, expected premium, probability, close date and lost reasons.
- Convert a lead into a client and quote in one action.
- Source attribution and conversion reporting.
- Automated follow-up sequences (P3).

### 3.4 Insurers (markets), products and classes of business (P1)
- Insurer directory: name, code, regulator registration, contacts, remittance bank details, payment terms (days), portal URL, and logo for quote comparison.
- **Classes of business**: motor private, motor commercial, medical, life, fire/property, WIBA, marine, engineering, liability, travel, and others. Tenants can add their own.
- **Products** per insurer and class, with:
  - rating basis (rate on sum insured, flat premium, per-member tiers, or manual);
  - minimum premium;
  - optional benefits and extensions, each with its own rate or flat amount;
  - excess or deductible text;
  - wording and policy document attachments.
- **Commission rate tables** per insurer × class × product, effective-dated, optionally tiered, with separate rates for new business and renewal.

### 3.5 Quotations (P1)
- **Generic quote** (Invoicing tier): line items (description, qty, unit price, discount, tax code), sections, optional items, notes, terms, validity date.
- **Insurance quote** (Broker tier): one or more **options**, each from an insurer and product. Each option holds:
  - sum insured, rate, basic premium, benefits or extensions, loadings and discounts;
  - computed levies, taxes and fees;
  - total payable, excess, key exclusions and commission (internal only, never shown to the client).
- The client-facing **comparison view** shows options side by side; the client selects one and accepts.
- States: `draft → sent → viewed → accepted | declined | expired → converted`. Revisions create a new version, and earlier versions are kept immutable.
- **Convert an accepted quote** into:
  - a policy in `pending` or `active` state;
  - a debit note (an invoice to the client);
  - renewal and payment reminders.
- Delivered as a PDF attachment and a trackable public link. Duplicating a quote and saving it as a template is supported.

### 3.6 Invoices, debit notes, credit notes and receipts (P1)
- **Invoice** (generic) and **debit note** (insurance premium billing, linked to a policy and insurer) share the same engine.
- **Credit notes** handle refunds, cancellations and negative endorsements, linked to the original document.
- States: `draft → issued → sent → viewed → partially_paid → paid`, plus `overdue` (computed) and `void`.
- Features:
  - recurring invoices (P2) for instalment plans and subscriptions;
  - instalment schedules for premiums, so a debit note can carry a payment plan;
  - late reminders and partial payments;
  - multi-currency with the exchange rate captured at issue;
  - tax lines driven by tax codes from the jurisdiction pack;
  - e-invoicing submission through the tax adapter where required;
  - storage of the returned control number, signature or QR code, which is then printed on the PDF.
- **Receipts** are generated automatically on payment, numbered, and sent to the client.

### 3.7 Payments (P1)
- Record manual payments: cash, bank transfer, cheque or mobile money with a reference.
- Online payment from public links:
  - **M-Pesa STK Push** (Daraja);
  - **cards** via Stripe and/or Paystack or Flutterwave (**[DECISION PENDING]** which regional provider);
  - the provider is configurable per tenant using the tenant's own merchant credentials.
- Webhooks are verified, stored, processed idempotently and reconciled automatically against invoices.
- Allocation: one payment can cover multiple invoices, and an invoice can receive multiple payments.
- Unallocated payments are treated as client credit.
- Refunds are recorded and linked to credit notes.

### 3.8 Policies (P1)
- Fields:
  - policy number (from the insurer), insurer, product, class, client, insured items or risks;
  - sum insured, period start and end, premium breakdown, payment plan, commission rate snapshot;
  - status, documents and certificates, and cover notes or stickers (jurisdiction-dependent, P2).
- **Risk items** use flexible structured data per class, defined by a JSON schema per class of business. Examples:
  - motor: registration, make, model, year, chassis, value;
  - medical: members with date of birth and relationship.
- **Endorsements** (P1) record mid-term changes: add or remove a risk, change sum insured or cover. Each endorsement produces a premium adjustment (pro-rata or short-period table) and a debit or credit note.
- **Renewals**: generate a renewal quote N days before expiry, compare expiring versus renewing terms, and track the renewal pipeline.
- **Cancellations** produce a pro-rata or short-period refund and a credit note.
- States: `pending → active → expired | renewed | cancelled | lapsed`.

### 3.9 Commissions (P1 calculation; P2 reconciliation)
- Commission is calculated on commissionable premium using the effective rate table, snapshotted onto the policy or endorsement.
- **Withholding tax on commission** and **VAT on commission** (where applicable) come from the jurisdiction pack.
- **Agent and sub-agent splits**: percentage or fixed, with multi-level splits for an agency and its agents.
- Commission ledger states: `expected → invoiced (to insurer, if applicable) → received → paid_out (to agent)`.
- **Insurer statement reconciliation** (P2):
  - upload a CSV, XLSX or PDF statement and map its columns (mappings are saved per insurer);
  - auto-match lines by policy number, amount and date, with a fuzzy-match suggestion queue;
  - resolve differences by accepting, disputing or adjusting;
  - variance reporting.
- Agent commission statements and payout runs (P2).

### 3.10 Premium remittance to insurers (P1)
- Track premium collected versus premium due to each insurer: either net of commission if the broker deducts commission, or gross. The method is configurable per insurer.
- Remittance batches: select paid debit notes, generate a remittance advice PDF, record payment to the insurer, and mark items as remitted.
- Aged payables to insurers. Overdue remittance alerts, since regulators often set premium remittance deadlines (**[VERIFY]** per jurisdiction).

### 3.11 Claims (P2)
- Claim registration against a policy: date of loss, type, description, estimated amount, documents and photos.
- States: `reported → submitted_to_insurer → under_review → approved | rejected → settled → closed`.
- Document checklist per class, insurer claim reference, settlement amount, excess applied, and a timeline of insurer correspondence.
- The client can report a claim and upload documents through the portal (P2).

### 3.12 Documents (P1)
- Upload to object storage via presigned URLs, with type and size validation and an optional virus scan hook.
- Documents link to any entity (client, policy, claim, quote, and so on) and carry tags, expiry dates and versions.
- Generated documents (PDFs) are stored with a hash so their integrity can be verified.
- Expiry reminders cover KYC documents, licences and certificates.

### 3.13 Tasks, reminders and notifications (P1)
- Tasks have an assignee, due date, priority and an optional link to an entity. Recurring tasks are P2.
- A **reminder rules engine**, configured per tenant:
  - renewal reminders, for example 60, 30, 14, 7 and 1 days before expiry, sent to the broker and/or the client;
  - premium instalment due, invoice overdue (for example 1, 7 and 14 days after due), quote expiring, document expiring;
  - each rule has channels (email, SMS, WhatsApp, in-app), a message template, quiet hours, and a deduplication key so the same reminder is never sent twice.
- In-app notification centre (bell icon), plus per-user notification preferences.
- An outbound message log records the channel, status (queued, sent, delivered, failed or read where the provider supports it), the provider ID and cost where available.

### 3.14 Templates and branding (P1 core, P2 marketplace polish)
- Document templates are **HTML/CSS (Jinja2)**. The same template renders the web view of a public link and the PDF.
- Each template declares in a manifest:
  - `id`, `name`, `tier` (`free` / `premium`), supported document types, layout variants;
  - design tokens (colours and fonts), a preview image, and paper size (A4 or Letter).
- Tenants pick a template per document type and apply their branding: logo, colours, font pair, footer, signature image, stamp, payment instructions and QR code.
- Ship with at least **8 templates** at launch (3 free, 5 premium), all print-quality and accessible. Fonts are self-hosted.
- Message templates (email, SMS, WhatsApp) per event, with variables and localisation.
- WhatsApp templates must also be pre-approved with Meta; store the approved template name.

### 3.15 Public links and client portal (P1 links, P2 portal)
- **Public document links**: `https://{app}/d/{token}`.
  - The token is 32+ random bytes; only its SHA-256 hash is stored.
  - Each link has an expiry and a scope (`view`, `accept`, `pay`), and links can be revoked.
  - Tracked events: `sent`, `delivered`, `opened`, `viewed` (with duration), `downloaded`, `accepted`, `declined`, `paid`.
  - Accepting captures the accepter's name, email or phone, timestamp, IP and user agent, plus a checkbox of agreement to the terms (simple e-acceptance).
  - Advanced e-signature integration is P3.
- **Client portal** (P2): magic link or OTP login. Clients see their policies, documents, invoices, payments and claims, and can make service requests (endorsement request, certificate request, claim report). Branded per tenant, optionally on a custom domain (P3).

### 3.16 Reports and dashboards (P1 basic, P2 full)
- Dashboard:
  - premiums written this month or year, collected versus outstanding;
  - commission earned versus received;
  - renewals due in the next 30 or 60 days, quotes awaiting response, overdue invoices, open claims.
- Reports, each filterable and exportable to CSV and XLSX:
  - production by insurer, class, broker, branch and period;
  - premiums issued, collected and remitted;
  - aged debtors (clients) and aged creditors (insurers);
  - commission statements, renewal retention and lapse rate;
  - quote conversion rate, claims summary;
  - regulator returns (P3; jurisdiction pack).

### 3.17 SaaS subscription billing and entitlements (P1)
- Plans: `invoicing_free`, `invoicing_pro`, `broker_starter`, `broker_pro`, `enterprise` (**[DECISION PENDING]** prices).
- Entitlements:
  - feature flags, seat limits, monthly document limits, premium template access;
  - SMS and WhatsApp credits (passed through or bundled), storage limits.
- Free trial (14 days of Broker Pro), upgrades and downgrades with proration, dunning, and invoices for our own subscription.
- Billing via Stripe Billing for card payments internationally. Optionally M-Pesa for local subscriptions (**[DECISION PENDING]**).
- The API enforces entitlements through a dependency such as `require_feature("commission_reconciliation")` and quota checks.

### 3.18 Audit log (P1)
- Append-only audit events record:
  - who (user ID, actor type), the tenant and what (entity, action);
  - the before and after diff for financial and policy records;
  - IP address, user agent, request ID and timestamp.
- Visible to owners and admins. Platform-admin access to tenant data is also logged.

### 3.19 Reinsurance (P3)
- **Facultative placements**: the original risk and cedent, the share offered, reinsurer participants with share percentages, ceded premium, reinsurance commission and brokerage.
- Placement slip PDF, firm or indicative quotes per reinsurer, and the binding status of each participant.
- Generated documents: debit and credit notes to the cedent and to reinsurers, and statements of account.
- Claim recoveries per reinsurer share.
- Treaty administration is out of scope until further notice.

### 3.20 AI features (P3)
- Extract structured policy data from uploaded insurer schedules or quotes (PDF) using the Claude API. A human reviews the result before saving, and confidence is shown per field.
- Renewal risk scoring, using signals such as payment history, claims and engagement with links.
- Draft client messages and summarise client history.
- AI usage is metered per tenant and can be switched off per tenant.

### 3.21 Data import and export (P1)
- Import clients, insurers, policies and opening balances from CSV or XLSX, with templates to download, a mapping UI, dry-run validation and an error file.
- Full tenant data export (ZIP of CSVs plus documents) to meet data-portability obligations.

---

## 4. System architecture

### 4.1 High-level view
```
          ┌──────────────┐  ┌───────────────┐  ┌────────────────────────┐
          │ Next.js web  │  │ Expo mobile   │  │ Public links / portal  │
          │ (shadcn/ui)  │  │ (P2)          │  │ (served by web)        │
          └──────┬───────┘  └──────┬────────┘  └───────────┬────────────┘
                 │  cookies (same-origin /api/auth/*)       │
                 ▼                  ▼                       ▼
          ┌──────────────────────────────┐      ┌─────────────────────────┐
          │ auth service (Better Auth,   │─JWKS─▶ FastAPI core API        │
          │ Hono, Node) → issues JWT     │      │ /api/v1 (OpenAPI 3.1)   │
          └──────────────┬───────────────┘      └───────┬─────────┬───────┘
                         │                              │         │ enqueue
                         ▼                              ▼         ▼
                 ┌─────────────────────────────────────────┐  ┌──────────────┐
                 │ PostgreSQL 17 (schemas: auth, app)      │  │ Redis        │
                 └─────────────────────────────────────────┘  └──────┬───────┘
                                                                     ▼
       ┌──────────────┐   ┌─────────────┐   ┌──────────────────────────────┐
       │ MinIO / S3   │◀──│ Gotenberg   │◀──│ Celery workers + Celery Beat │
       │ (documents)  │   │ (HTML→PDF)  │   │ PDFs, reminders, webhooks,   │
       └──────────────┘   └─────────────┘   │ imports, tax submission      │
                                            └──────────────┬───────────────┘
                                                           ▼
            External: Stripe · M-Pesa Daraja · Paystack/Flutterwave · KRA eTIMS ·
            Email (Resend/Postmark; Mailpit in dev) · SMS (Africa's Talking) ·
            WhatsApp Cloud API · Claude API (P3)
```

### 4.2 Architectural style
- The backend is a **modular monolith**. One FastAPI deployable, with code organised by domain module and clear boundaries. Modules talk to each other through service functions and domain events, never by reaching into another module's tables in ad-hoc queries.
- **Domain events** use an outbox: the event is written to an `outbox_events` table in the same transaction as the change, and a worker dispatches it. This drives notifications, reminders, webhooks to tenants (P3), audit and search indexing.
- Workers share the API's codebase and image and use a different entrypoint.

### 4.3 Technology stack (use latest stable versions at project start; pin exact versions in lockfiles)
| Concern | Choice |
|---|---|
| Backend language | Python 3.13 |
| Package manager | `uv` (lockfile committed) |
| Web framework | FastAPI, with Pydantic v2 and pydantic-settings |
| ORM / migrations | SQLAlchemy 2.x (typed, `Mapped[]`) with Alembic |
| DB driver | psycopg 3 (async for the API, sync for Celery tasks — one driver) |
| Database | PostgreSQL 17, with `pg_trgm`, `citext`, `pgcrypto` extensions |
| Cache / broker | Redis 7 (or Valkey) |
| Background jobs | Celery 5, with Celery Beat for schedules |
| PDF | Gotenberg (Chromium) rendering HTML generated from Jinja2 templates |
| Object storage | S3-compatible: MinIO in dev, Cloudflare R2 or AWS S3 in prod |
| Auth | Better Auth in a standalone Node service (Hono), issuing JWTs verified by FastAPI via JWKS (see §7) |
| Email (dev) | Mailpit |
| Lint / format / types | ruff, mypy `--strict` (or pyright strict) |
| Tests | pytest, pytest-asyncio, httpx `AsyncClient`, factory-boy, `freezegun`/`time-machine`, `respx` (HTTP mocking), `schemathesis` (OpenAPI contract fuzzing), hypothesis (calculation properties) |
| Observability | structlog (JSON logs), OpenTelemetry traces (optional exporter), Sentry, Prometheus metrics endpoint |
| Frontend | Next.js (latest stable, App Router, React Server Components), TypeScript strict, Tailwind CSS v4, **shadcn/ui**, lucide-react, TanStack Query, TanStack Table, react-hook-form with zod, next-intl, next-themes, sonner, shadcn charts (Recharts) |
| API client | Generated from `openapi.json` with `@hey-api/openapi-ts` (or orval) into `packages/api-client` |
| Mobile (P2) | React Native with Expo (Expo Router), sharing `packages/api-client` and zod schemas; Better Auth Expo client |
| Monorepo | pnpm workspaces with Turborepo for the TS apps; `uv` for Python |
| CI | GitHub Actions: lint, typecheck, test in Compose, build images, OpenAPI diff check |

### 4.4 Repository layout
```
/
├── CLAUDE.md                    # short agent rules → points to docs/PROJECT_SPEC.md
├── compose.yaml                 # all runtime services
├── compose.test.yaml            # test overrides + api-tests / e2e runners
├── compose.override.example.yaml
├── .env.example
├── Makefile                     # make up, make test, make migrate, make openapi, make lint
├── docs/
│   ├── PROJECT_SPEC.md          # this file
│   ├── adr/
│   └── runbooks/
├── apps/
│   ├── api/                     # FastAPI + Celery (Python)
│   ├── auth/                    # Better Auth service (Node, Hono)
│   ├── web/                     # Next.js + shadcn/ui
│   └── mobile/                  # Expo (P2)
├── packages/
│   ├── api-client/              # generated TS client + types
│   └── config/                  # shared eslint/tsconfig/tailwind presets
└── .github/workflows/
```

### 4.5 Backend layout (`apps/api`)
```
apps/api/
├── pyproject.toml / uv.lock
├── Dockerfile                   # multi-stage; non-root user; targets: api, worker, test
├── alembic.ini, migrations/
├── app/
│   ├── main.py                  # app factory, routers, middleware, lifespan
│   ├── core/
│   │   ├── config.py            # pydantic-settings
│   │   ├── db.py                # engines, session factories, tenant context (SET LOCAL)
│   │   ├── auth.py              # JWKS verification, current principal dependency
│   │   ├── permissions.py       # permission registry, require_permission()
│   │   ├── entitlements.py      # require_feature(), quotas
│   │   ├── errors.py            # RFC 9457 problem+json handlers
│   │   ├── money.py             # Money type, rounding, currency helpers
│   │   ├── ids.py               # UUIDv7
│   │   ├── pagination.py        # cursor pagination
│   │   ├── idempotency.py       # Idempotency-Key middleware/store
│   │   ├── numbering.py         # gapless document number allocation
│   │   ├── audit.py, outbox.py, logging.py, telemetry.py
│   ├── modules/
│   │   ├── tenants/  clients/  leads/  insurers/  products/
│   │   ├── quotes/  billing/ (invoices, debit/credit notes, receipts)
│   │   ├── payments/  policies/  commissions/  remittances/
│   │   ├── claims/  documents/  tasks/  reminders/  notifications/
│   │   ├── templates/  public_links/  reports/  imports/
│   │   ├── subscriptions/  audit/  jurisdictions/  reinsurance/ (P3)
│   │   └── <module>/{models.py, schemas.py, service.py, router.py, tasks.py, events.py, README.md}
│   ├── calc/                    # pure calculation engine (no I/O): premium, levies, tax, commission, pro-rata
│   ├── integrations/
│   │   ├── payments/{base.py, stripe.py, mpesa.py, paystack.py}
│   │   ├── tax/{base.py, kra_etims.py, noop.py}
│   │   ├── messaging/{email.py, sms_africastalking.py, whatsapp_cloud.py}
│   │   ├── storage/s3.py
│   │   ├── pdf/gotenberg.py
│   │   └── ai/claude.py (P3)
│   ├── jurisdictions/packs/     # versioned YAML/JSON packs: ke/, generic/ …
│   ├── document_templates/      # Jinja2 HTML/CSS templates + manifests + fonts
│   └── workers/{celery_app.py, beat_schedule.py}
└── tests/
    ├── unit/                    # calc, state machines, numbering, permissions
    ├── integration/             # API + DB + Redis + MinIO + Mailpit
    ├── contract/                # schemathesis against openapi
    ├── e2e/                     # through auth service → API in compose
    ├── factories/  conftest.py
```

---

## 5. Backend engineering standards

### 5.1 API conventions
- Base path `/api/v1`. Breaking changes require `/api/v2` or additive evolution.
- OpenAPI 3.1, auto-generated, with operation IDs `module_action` (for example `quotes_create`) so the generated client is clean.
- JSON naming is **snake_case**. The generated TS client keeps snake_case (no remapping), to avoid ambiguity.
- Errors use **RFC 9457** `application/problem+json`, with `type`, `title`, `status`, `detail`, `instance`, plus `code` (a stable machine code) and `errors[]` for field validation.
- Pagination is **cursor-based** (`?limit=&cursor=`), and responses carry `next_cursor`. Filtering uses explicit query params; sorting uses a whitelisted `?sort=-created_at`.
- **Idempotency**: `Idempotency-Key` is required on POSTs that create financial records or trigger payments or sends. Keys are stored for 24h with the response replayed.
- **Optimistic concurrency**: mutable resources have a `version` integer. Updates require an `If-Match` header or a `version` field, and a mismatch returns 409.
- Money in JSON is `{"amount": "1234.50", "currency": "KES"}`, with the amount as a string.
- Timestamps are ISO 8601 UTC (`timestamptz`). Dates without times (policy periods) are `date`.
- Rate limiting is per-IP for public endpoints (public links, lead forms) and per-tenant for API keys. Return `429` with `Retry-After`.
- Health endpoints: `GET /health/live` (process up) and `GET /health/ready` (DB, Redis, storage reachable).
- Every response carries an `X-Request-ID`, propagated into logs.

### 5.2 Data and persistence
- Primary keys are **UUIDv7**, which are time-ordered.
- Every tenant table has `tenant_id uuid not null`, `created_at`, `updated_at`, `created_by`, `updated_by` and `version`. Soft delete (`deleted_at`) applies only to non-financial master data such as clients, leads and tasks.
- **Row-Level Security**:
  - The API connects as role `app_user`, which is not a superuser and not the table owner.
  - Each request transaction runs `SET LOCAL app.tenant_id = '<uuid>'`.
  - Policies are `USING (tenant_id = current_setting('app.tenant_id')::uuid)`, with a matching `WITH CHECK`.
  - Migrations run as `app_owner`.
  - Platform-admin and cross-tenant jobs use a separate, audited role or connection with `BYPASSRLS`, only where strictly needed.
- **Money**: `NUMERIC(20,4)` for rates and intermediate amounts and `NUMERIC(20,2)` for stored monetary totals, with a currency code column. Rounding rules come from the jurisdiction pack (default ROUND_HALF_UP to 2 dp at line level, and the total is the sum of the rounded lines).
- **Gapless numbering**: a `number_sequences` table (tenant, branch, document type, period) with `SELECT … FOR UPDATE` allocation inside the issuing transaction.
- **Ledger**: a double-entry `ledger_entries` table with `journal_id`, `account`, `debit`, `credit`, `currency`, `entity_ref`. Accounts include client receivable, insurer payable, commission receivable, commission income, agent commission payable, tax payable, cash/bank and unallocated cash.
  - Every issued debit or credit note, payment, remittance and commission event posts a balanced journal.
  - Reports read from the ledger plus document tables.
  - A balance check is enforced in tests (total debits equal total credits per journal).
- Use JSONB only for flexible risk details and template settings, validated by JSON Schema or Pydantic before writing.
- Search: Postgres full-text plus `pg_trgm` for client and policy lookup. No external search engine in P1.
- Sensitive PII (national ID or passport numbers, date of birth for medical members) uses application-level encryption (AES-GCM, key from env or KMS), plus a keyed hash column for exact-match lookup.

### 5.3 Code quality
- Type-annotate everything. `mypy --strict` passes. Avoid `Any` and use `typing.Protocol` for adapter interfaces.
- Services are plain functions or classes that take an explicit `session` and `principal`. Routers are thin: parse, authorise, call the service, map the response.
- The calculation engine (`app/calc`) is **pure**: no DB or HTTP access. It uses `Decimal`, is deterministic, and is property-tested with hypothesis.
- State machines are explicit transition tables, unit-tested for every allowed and forbidden transition.
- Domain exceptions map to problem+json codes in one place.
- Configuration comes from environment variables only (12-factor). No settings are read at import time outside `config.py`.
- Logs are structured JSON with `request_id`, `tenant_id` and `user_id`. Never log secrets, tokens or full PII.

### 5.4 Background jobs
- Celery queues: `default`, `pdf`, `messaging`, `webhooks`, `imports`, `tax`.
- Every task is **idempotent**: it takes entity IDs (never ORM objects), re-fetches state and checks status before acting.
- Retries use exponential backoff and jitter. Exhausted tasks go to a dead-letter queue, with a failed-job record visible to platform admins.
- Celery Beat schedules:
  - reminder scan (every 15 min, respecting tenant timezone and quiet hours);
  - overdue invoice recompute (hourly);
  - policy expiry and lapse (daily);
  - outbox dispatcher (every few seconds, or a long-running consumer);
  - quote expiry (hourly), subscription checks (daily) and storage cleanup.

### 5.5 Security baseline
- Target **OWASP ASVS Level 2**.
- Strict CORS (web origin only). Security headers (HSTS, CSP on the web app, X-Content-Type-Options). Secure, HttpOnly, SameSite=Lax cookies for web sessions.
- JWT verification checks signature (via JWKS, with a cached refresh when an unknown `kid` arrives), `iss`, `aud`, `exp`, `nbf`, and a required `org_id` claim for tenant routes.
- Uploads:
  - MIME sniffing plus an extension allowlist and a size limit;
  - presigned PUT URLs that expire within 10 min;
  - downloads only via short-lived presigned GET URLs after a permission check;
  - optional ClamAV scan hook in P2.
- Public link tokens are hashed at rest and compared in constant time. They can be revoked, and no internal IDs appear in public URLs.
- Webhook endpoints verify provider signatures (Stripe signature, Daraja callback validation, Paystack HMAC), store the raw payload and process it asynchronously.
- Secrets live in environment variables in dev and a secrets manager in prod.
- Dependency scanning (pip-audit, npm audit / osv-scanner) runs in CI. Container images are scanned with Trivy.
- **Data protection**: comply with Kenya's Data Protection Act 2019 and GDPR-style principles. This covers consent records, purpose limitation, data subject export and deletion (deletion is anonymisation where retention law requires keeping financial records), retention policies per entity, breach logging, and registration with the regulator where required (**[VERIFY]**).

---

## 6. Domain model and calculations

### 6.1 Core entities (P1 unless stated)
```
Tenant(id, name, legal_name, tax_pin, regulator_licence_no, licence_expiry, country, default_currency,
       timezone, locale, jurisdiction_pack, plan, settings jsonb)
Branch(id, tenant_id, name, code, tax_branch_id, numbering_prefix)
Membership — mirrored from auth (user_id, org_id, role); API keeps tenant_user_profiles for preferences

Client(id, tenant_id, type[individual|corporate], display_name, first/last/company name, id_number_enc,
       id_number_hash, tax_pin, dob, emails[], phones[], preferred_channel, address jsonb, industry,
       source, tags[], assigned_user_id, consent_marketing_at, consent_comms_at, deleted_at)
ClientContact(id, client_id, name, role, email, phone, is_primary)

Lead(id, tenant_id, client_id?, name, contact, class_of_business_id, expected_premium Money, stage_id,
     probability, expected_close, source, lost_reason, assigned_user_id)  [P2]
PipelineStage(id, tenant_id, name, order, is_won, is_lost)  [P2]

Insurer(id, tenant_id, name, code, regulator_no, contacts jsonb, bank_details jsonb, remittance_terms_days,
        remittance_method[gross|net_of_commission], logo_document_id)
ClassOfBusiness(id, tenant_id?, code, name, risk_schema jsonb)    -- global defaults + tenant custom
Product(id, tenant_id, insurer_id, class_id, name, rating_basis, rate, min_premium, benefits jsonb, excess_text)
CommissionRate(id, tenant_id, insurer_id, class_id, product_id?, business_type[new|renewal],
               rate, effective_from, effective_to)

Quote(id, tenant_id, number?, kind[generic|insurance], client_id, status, version, parent_quote_id,
      valid_until, currency, template_id, notes, terms, accepted_option_id, accepted_at, acceptance jsonb)
QuoteLine(id, quote_id, description, qty, unit_price, discount, tax_code, sort)        -- generic
QuoteOption(id, quote_id, insurer_id, product_id, sum_insured, risk_details jsonb, premium_breakdown jsonb,
            total_payable, commission_rate, commission_amount, sort)                   -- insurance

Policy(id, tenant_id, policy_number, client_id, insurer_id, product_id, class_id, status,
       period_start, period_end, sum_insured, currency, premium_breakdown jsonb, gross_premium,
       commission_rate_snapshot, commission_amount, payment_plan jsonb, source_quote_id,
       renewed_from_policy_id, assigned_user_id)
PolicyRisk(id, policy_id, risk_type, details jsonb, sum_insured, premium)
Endorsement(id, policy_id, number, type, effective_date, description, premium_delta, method[pro_rata|short_period|flat],
            debit_or_credit_note_id, status)

BillingDocument(id, tenant_id, type[invoice|debit_note|credit_note], number, status, client_id, policy_id?,
                endorsement_id?, insurer_id?, issue_date, due_date, currency, fx_rate, subtotal, tax_total,
                levy_total, total, amount_paid, balance, related_document_id?, template_id,
                tax_submission_status, tax_control_number, tax_qr_payload, pdf_document_id)
BillingLine(id, billing_document_id, description, qty, unit_price, discount, tax_code, line_type
            [item|premium|levy|tax|fee], amount, commissionable bool)
InstalmentSchedule(id, billing_document_id, seq, due_date, amount, status)

Payment(id, tenant_id, number, client_id, method[mpesa|card|bank|cash|cheque], provider, provider_ref,
        amount, currency, received_at, status[pending|succeeded|failed|refunded], raw_event_id)
PaymentAllocation(id, payment_id, billing_document_id, amount)
Receipt(id, tenant_id, number, payment_id, pdf_document_id)

CommissionEntry(id, tenant_id, policy_id, endorsement_id?, insurer_id, gross_commission, wht, vat,
                net_commission, status[expected|invoiced|received|paid_out], statement_line_id?)
CommissionSplit(id, commission_entry_id, user_id|agent_id, share_type[percent|fixed], value, amount, payout_id?)
InsurerStatement(id, tenant_id, insurer_id, period, file_document_id, mapping_id, status)      [P2]
InsurerStatementLine(id, statement_id, policy_number, amount, date, raw jsonb, match_status, matched_entry_id) [P2]

Remittance(id, tenant_id, insurer_id, number, period, total_gross, total_commission_deducted, total_net,
           status[draft|approved|paid], paid_at, reference, advice_pdf_id)
RemittanceItem(id, remittance_id, billing_document_id, gross, commission, net)

Claim(id, tenant_id, number, policy_id, client_id, loss_date, reported_at, type, description,
      estimate, insurer_claim_ref, status, settled_amount, excess_applied)  [P2]

Document(id, tenant_id, entity_type, entity_id, kind, filename, mime, size, storage_key, sha256,
         expires_at, version, uploaded_by)
Task(id, tenant_id, title, description, assignee_id, due_at, priority, status, entity_type, entity_id)
ReminderRule(id, tenant_id, event_type, offsets_days[], audience[broker|client], channels[], message_template_id,
             enabled)
ScheduledReminder(id, tenant_id, rule_id, entity_type, entity_id, fire_at, dedupe_key unique, status)
OutboundMessage(id, tenant_id, channel, to, template_id, payload jsonb, provider, provider_id, status, cost,
                error, sent_at, delivered_at, read_at)
Notification(id, tenant_id, user_id, type, title, body, entity_ref, read_at)

DocumentTemplate(id, key, name, tier, doc_types[], manifest jsonb, version)   -- global catalogue
TenantTemplateSetting(tenant_id, doc_type, template_id, branding_overrides jsonb)
MessageTemplate(id, tenant_id?, channel, event_type, locale, subject, body, whatsapp_template_name)

PublicLink(id, tenant_id, token_hash, entity_type, entity_id, scopes[], expires_at, revoked_at)
LinkEvent(id, public_link_id, type, occurred_at, ip, user_agent, meta jsonb)

Subscription(id, tenant_id, plan, status, provider, provider_customer_id, provider_subscription_id,
             trial_ends_at, current_period_end, seats)
UsageCounter(tenant_id, metric, period, value)

AuditEvent(id, tenant_id, actor_type, actor_id, action, entity_type, entity_id, diff jsonb, ip, ua,
           request_id, occurred_at)
OutboxEvent(id, tenant_id, type, payload jsonb, created_at, dispatched_at, attempts)
WebhookEvent(id, provider, event_id unique, payload jsonb, received_at, processed_at, status)
IdempotencyKey(key, tenant_id, request_hash, response jsonb, created_at)
NumberSequence(tenant_id, branch_id?, doc_type, period_key, next_value)
LedgerJournal(id, tenant_id, occurred_at, source_type, source_id, memo)
LedgerEntry(id, journal_id, account, debit, credit, currency, client_id?, insurer_id?, policy_id?)

ReinsurancePlacement / ReinsuranceParticipant  [P3]
```

### 6.2 Premium calculation (insurance quote option, policy, endorsement)
All arithmetic uses `Decimal`; the rounding mode comes from the jurisdiction pack.
```
basic_premium = per rating_basis:
    rate_on_sum_insured: sum_insured × rate        (rate stored as decimal, e.g. 0.035 = 3.5%)
    flat:               product flat amount
    tiered / per_member: Σ tier amounts
    manual:             entered value
basic_premium = max(basic_premium, min_premium)
benefits_total = Σ benefit (rate × base or flat)
adjusted_premium = basic_premium + benefits_total + loadings − discounts      (never below min_premium unless override with permission)
levies = for each levy rule applicable to (class, jurisdiction, date):
    basis ∈ {premium, sum_insured, flat}; amount = basis × rate or flat; apply min/max; round
taxes = per tax rule (if any apply to premium in the jurisdiction)
fees  = policy/admin fees (tenant-configurable; commissionable flag false by default)
total_payable = adjusted_premium + Σ levies + Σ taxes + Σ fees
```
The output is a `premium_breakdown` JSON listing every component, the rule that produced it (ID and version) and the rounding applied. This makes every amount reproducible and auditable.

### 6.3 Commission
```
commissionable_premium = Σ components flagged commissionable (default: adjusted_premium only; levies & fees excluded)
rate = override_rate (requires permission) or CommissionRate effective on policy start (new vs renewal)
gross_commission = round(commissionable_premium × rate)
wht_on_commission = gross_commission × wht_rate (jurisdiction pack; resident/non-resident)
vat_on_commission = gross_commission × vat_rate if pack says commission is VATable, else 0
net_commission_receivable = gross_commission − wht (+ vat if invoiced to insurer)
splits: Σ split amounts ≤ gross_commission; remainder = agency retained
```

### 6.4 Endorsements, cancellations and refunds
```
pro_rata_factor = remaining_days / total_days     (day count convention from pack: actual/365 default)
short_period: lookup factor table from pack/insurer by elapsed period
premium_delta = (new_annual_premium − old_annual_premium) × factor
levies/taxes recalculated on the delta per pack rules (some levies non-refundable — pack flag)
delta > 0 → debit note; delta < 0 → credit note; commission adjusted proportionally (clawback on refunds)
```

### 6.5 State machines
```
Quote:     draft → sent → viewed → {accepted, declined, expired}; accepted → converted; any non-final → draft (new version)
Billing:   draft → issued → sent → viewed → partially_paid → paid; issued+ → void (only if unpaid; else credit note)
           overdue = computed flag (due_date < today AND balance > 0)
Policy:    pending → active → {expired, renewed, cancelled, lapsed}; active → active (endorsement)
Claim:     reported → submitted_to_insurer → under_review → {approved, rejected}; approved → settled → closed; rejected → closed
Payment:   pending → {succeeded, failed}; succeeded → refunded (partial allowed via refund records)
Remittance: draft → approved → paid
```

### 6.6 Jurisdiction packs
Packs are versioned data files (`app/jurisdictions/packs/{country}/{version}.yaml`) that are loaded into DB tables on startup or migration. A tenant selects a pack, and rules are effective-dated. Each pack contains:
- currency, rounding mode and precision, and day-count convention;
- tax codes (VAT standard, exempt, zero-rated), whether insurance premiums are VAT-exempt, and whether broker commission is VATable;
- withholding tax rates on commission (resident and non-resident);
- statutory levies per class: name, basis, rate, min/max, refundable flag and commissionable flag;
- required client and document fields (for example a tax PIN on invoices) and numbering-format constraints;
- e-invoicing adapter key and its required fields;
- the short-period cancellation table;
- the premium remittance deadline in days;
- regulator report definitions (P3).

**Kenya pack (`ke`) seed values — all [VERIFY] with current IRA / KRA rules before seeding:**
- Training levy of about 0.2% of premium and Policyholders' Compensation Fund levy of about 0.25% of premium, applying to most general insurance classes.
- Stamp duty as a flat amount per policy for some classes.
- Insurance premiums generally VAT-exempt; broker commission/services VAT treatment and withholding tax on commission per current KRA rules.
- eTIMS e-invoicing mandatory for VAT-registered businesses. Integrate via OSCU/VSCU or the API in the KRA sandbox first.
- Premium remittance deadline per IRA rules.

A `generic` pack (no levies, a configurable VAT rate, no e-invoicing) serves Invoicing-tier users anywhere.

---

## 7. Authentication and authorisation

### 7.1 Decision
- **Better Auth** runs in a **standalone Node service** (`apps/auth`, a Hono server) so the backend can be developed and tested end to end before the web app exists. The same service serves web and mobile.
- The web app proxies `/api/auth/*` to the auth service through Next.js rewrites, so cookies stay same-origin.
- Better Auth stores its tables in the same Postgres, in a separate `auth` schema, owned by a separate DB role that the API cannot write to.

### 7.2 Better Auth configuration
- Email and password, with email verification required and secure password reset.
- Social sign-on: **Google**, **Microsoft** (Entra, which suits corporate brokers) and **Apple** (needed for iOS).
- Plugins:
  - `organization` (tenants, members, roles, invitations);
  - `twoFactor` (TOTP plus backup codes; required for `owner` and `accounts` roles, enforced by the API using an `amr` or `2fa` claim);
  - `passkey`, `phoneNumber` (OTP via SMS; useful in mobile-first markets), `magicLink` (client portal users);
  - `jwt` (issues short-lived access tokens and exposes `/api/auth/jwks`), `bearer` (for mobile);
  - the Expo integration (P2), and `sso` (SAML/OIDC, Enterprise plan, P3).
- Rate limiting is enabled, with secure cookie settings and trusted origins configured.
- JWT claims, customised through the jwt plugin's `definePayload`: `sub` (user ID), `email`, `name`, `org_id` (active organization), `org_role`, `perms_version`, `mfa` (bool), `iss`, `aud`. Expiry is about 15 minutes. EdDSA is the default algorithm; key rotation is automatic.
- Hooks: on organization creation, call the API's internal endpoint `POST /internal/tenants` (authenticated with a service token over the internal network) to provision the tenant, default roles, numbering sequences, default reminder rules and the default template selection. The API also provisions lazily on the first request with an unknown `org_id`, as a fallback.

### 7.3 API side
- A `current_principal` dependency verifies the JWT against the cached JWKS (refetching on an unknown `kid`), then resolves tenant membership and the permissions for `org_role`.
- It sets `SET LOCAL app.tenant_id` on the request's DB transaction.
- `require_permission("quote:create")` and `require_feature("...")` are FastAPI dependencies.
- Client-portal principals carry `actor_type=portal_client` and a `client_id`. They can only reach `/api/v1/portal/*` routes.
- Public-link access uses the link token, not a JWT, and is limited to `/api/v1/public/*` routes.
- API keys for tenant integrations (lead forms, P3 public API) are hashed and scoped, managed in the API's own table.

### 7.4 Testing auth
- Unit and integration tests use a **test JWKS fixture**: generate a keypair in tests, serve it with `respx`, and mint tokens with arbitrary claims. This makes testing every role and permission fast.
- E2E tests in Compose go through the real auth service: sign up, verify email via Mailpit's API, create an organization, fetch a JWT, call the API, and assert the tenant was provisioned and RLS is in effect.

---

## 8. Integrations (adapter pattern)

Every external system sits behind a `Protocol` in `app/integrations/*/base.py`. Each one has:
- a **fake or in-memory implementation**, used in tests and selectable through env (`PAYMENTS_PROVIDER=fake`);
- a real implementation, tested with `respx`-recorded HTTP interactions plus optional sandbox smoke tests marked `@pytest.mark.sandbox`. Sandbox tests are skipped unless credentials are present.

| Adapter | Interface (key methods) | Implementations |
|---|---|---|
| Payments | `create_payment_intent(invoice, amount, method, customer) → PaymentIntent`, `verify_webhook(headers, body) → Event`, `refund(payment, amount)` | `fake`, `stripe`, `mpesa_daraja` (STK Push + C2B callbacks), `paystack` / `flutterwave` **[DECISION PENDING]** |
| SaaS billing | `create_checkout(plan, tenant)`, `customer_portal_url(tenant)`, webhook → subscription state | `fake`, `stripe_billing` |
| Tax e-invoicing | `submit_invoice(doc) → TaxSubmissionResult(control_no, qr_payload, signature)`, `submit_credit_note`, `status(ref)` | `noop`, `fake`, `kra_etims` (sandbox first) |
| Email | `send(to, subject, html, text, attachments, headers)` | `smtp` (Mailpit in dev), `resend` or `postmark` |
| SMS | `send(to, text) → provider_id`, delivery-report webhook | `fake`, `africastalking` |
| WhatsApp | `send_template(to, template_name, locale, params)`, `send_session_message`, status webhook | `fake`, `whatsapp_cloud` (Meta Cloud API) |
| Storage | `presign_put`, `presign_get`, `put_bytes`, `delete`, `head` | `s3` (MinIO in dev and test) |
| PDF | `html_to_pdf(html, assets, paper) → bytes` | `gotenberg` |
| AI (P3) | `extract_policy(pdf_bytes, schema) → ExtractionResult` | `fake`, `claude` |

**Webhook flow:**
1. The endpoint verifies the signature and inserts into `webhook_events`; a unique `(provider, event_id)` constraint dedupes repeats.
2. It returns `200` quickly.
3. A Celery task processes the event, makes the domain changes, and posts the ledger journal.
4. Everything is reprocessable from the admin console.

**M-Pesa specifics:**
- STK Push to the client's phone, with the account reference set to the invoice number.
- Validate callbacks against the original request (`CheckoutRequestID`) and confirm via the status query API before marking an invoice paid.
- Store `MpesaReceiptNumber`.
- C2B Paybill/Till payments use the invoice number as the account number for auto-allocation, with an unmatched queue for payments that don't match.

---

## 9. Document generation and templates

- The pipeline:
  1. Load the entity, then build a typed **view model** (Pydantic). Templates never touch the ORM.
  2. Render the Jinja2 template with the tenant's branding tokens.
  3. Gotenberg (Chromium) produces the PDF.
  4. Store it in S3 with its SHA-256 hash.
  5. Link it as a `Document` and cache it per document version.
- The public link page renders **the same HTML** inside the web app, either through an API endpoint that returns the rendered HTML fragment or by the web app rendering the view model with matching React components. **Decision:** the API returns the rendered HTML for the public view, so web and PDF are pixel-consistent. The web app wraps it with action bar components (Accept, Pay, Download) built in shadcn.
- Each template folder has `manifest.json`, `template.html.j2`, `styles.css`, `preview.png` and `fonts/`.
- Templates use CSS custom properties for brand tokens, `@page` rules for paper size and margins, repeating table headers, and page numbers via Chromium's header/footer templates.
- Required template blocks:
  - header (logo, company details, tax PIN, licence number);
  - document meta (number, dates, status stamp), client block;
  - line items or premium breakdown, totals, tax summary;
  - payment instructions (bank and M-Pesa), QR codes (payment link and tax QR);
  - terms and footer.
- Template snapshot tests: render each template with fixture data to HTML and compare against a stored snapshot. Render to PDF in the Compose test run and assert the page count is greater than zero and key text is present (extracted with `pypdf`).
- Templates must handle long names, 100+ lines, RTL-safe text, and multiple currencies.

---

## 10. Docker Compose

### 10.1 Services (`compose.yaml`)
| Service | Image / build | Notes |
|---|---|---|
| `postgres` | `postgres:17` | init script creates roles `app_owner`, `app_user`, `auth_owner`, schemas `app`, `auth`, extensions; healthcheck `pg_isready` |
| `redis` | `redis:7-alpine` | healthcheck `redis-cli ping` |
| `minio` | `minio/minio` | plus `minio-init` (mc) to create buckets `documents`, `public-assets`; healthcheck |
| `mailpit` | `axllent/mailpit` | SMTP 1025, UI 8025, API for tests |
| `gotenberg` | `gotenberg/gotenberg:8` | internal only |
| `migrate` | build `apps/api` target `api` | one-shot `alembic upgrade head` then exits; others `depends_on: condition: service_completed_successfully` |
| `api` | build `apps/api` target `api` | `uvicorn app.main:app` (or `fastapi run`), port 8000, healthcheck `/health/ready` |
| `worker` | build `apps/api` target `worker` | `celery -A app.workers.celery_app worker -Q default,pdf,messaging,webhooks,imports,tax` |
| `beat` | build `apps/api` target `worker` | `celery beat` (single instance) |
| `auth` | build `apps/auth` | port 3001, healthcheck, runs Better Auth migrations on start (or a separate one-shot) |
| `web` | build `apps/web` | port 3000 (added after backend milestones) |

Conventions:
- All services are on an internal network, and only `web`, `api` (dev), `auth` (dev), `mailpit` UI and `minio` console publish ports.
- Configuration comes from `.env` through `env_file`.
- Every long-running service has a healthcheck, and `depends_on` uses `condition: service_healthy`.
- Dockerfiles are multi-stage with slim bases and run as a non-root user. `uv sync --frozen` is used for Python and a pnpm-deploy pattern for Node.
- `compose.override.yaml` (gitignored; example provided) adds dev bind mounts and hot reload.

### 10.2 Test setup (`compose.test.yaml`)
- Uses separate volumes (or tmpfs for Postgres data) for speed and isolation, and a separate DB name, `app_test`.
- `api-tests` service builds the `test` target with dev dependencies and runs:
  ```
  alembic upgrade head && pytest -n auto --cov=app --cov-report=term-missing --cov-fail-under=85 tests/unit tests/integration tests/contract
  ```
- `e2e-tests` service runs `pytest tests/e2e` against the live `auth` and `api` services.
- Test isolation:
  - Each integration test runs inside a transaction that is rolled back, with a SAVEPOINT pattern for code that commits.
  - RLS tests open real connections as `app_user` to prove isolation.
  - MinIO buckets are prefixed per test session.
  - Mailpit is purged between tests through its API.
- Commands, wrapped in the Makefile:
  ```
  make test        # docker compose -f compose.yaml -f compose.test.yaml run --rm api-tests
  make e2e         # ... run --rm e2e-tests
  make test-all    # both, then down -v
  ```
- CI (GitHub Actions) runs `make lint`, `make typecheck`, `make test-all`, the OpenAPI diff, and image builds with a Trivy scan.

### 10.3 Required test coverage areas (backend)
1. **Calculation engine**:
   - table-driven tests for every rating basis, levy rule, rounding mode, commission, WHT, pro-rata and short-period case;
   - hypothesis properties: totals equal the sum of components, no negative premium without a credit context, splits never exceed commission.
2. **State machines**: every allowed and forbidden transition.
3. **Numbering**: gapless and unique under concurrency (run 50 parallel issues and assert no gaps or duplicates).
4. **RLS / tenancy**: for each module, a user from tenant A gets 404 on tenant B's records for list, get, update and delete, and direct SQL as `app_user` without `app.tenant_id` returns zero rows.
5. **Permissions**: role × endpoint matrix tests, generated from the permission registry.
6. **Ledger**: every financial operation posts balanced journals, and report totals reconcile with the ledger.
7. **Idempotency**: repeated POSTs with the same key return the same response and create no duplicates. Duplicate webhooks are processed once.
8. **Payments**: the fake provider covers the full flow (link → intent → webhook → allocation → receipt → ledger), plus partial and over-payment.
9. **Documents / PDF**: generation through Gotenberg, storage in MinIO, presigned download, and the public link view-tracking events.
10. **Reminders**: time-travel tests (`time-machine`) covering timezone and quiet hours, deduplication, and channel fallbacks.
11. **Imports**: valid file, file with errors (error report produced), and a large file (10k rows) completing within the time budget.
12. **Contract**: schemathesis runs against `openapi.json` with authenticated fixtures and finds no 500s.
13. **E2E**: sign up → org → tenant provisioned → create client → insurance quote with two options → send (email in Mailpit) → open the public link → accept → convert to policy and debit note → pay with the fake provider → receipt emailed → commission entry expected → remittance batch → report totals correct.

---

## 11. Frontend (after backend milestones pass)

### 11.1 Stack and standards
- Next.js App Router with TypeScript `strict`, Tailwind CSS v4, and **shadcn/ui** for all base components, installed with the shadcn CLI into `apps/web/components/ui`.
- Use shadcn primitives and blocks: Sidebar, Data Table (TanStack Table), Form (react-hook-form + zod), Dialog, Sheet, Command (⌘K global search), Tabs, Calendar/Date Picker, Popover, Combobox, Badge, Card, Chart, Sonner toasts, Skeleton and Breadcrumb.
- Extend the shadcn components rather than replacing them. Keep a design-token layer (CSS variables) for light and dark themes with next-themes.
- Data fetching:
  - Server Components fetch through the generated client server-side, with the token taken from the session.
  - Client mutations use TanStack Query, with optimistic updates where safe.
  - Pass `Idempotency-Key` for financial mutations.
- Forms use zod schemas generated from or aligned with OpenAPI, with field-level server errors mapped from problem+json `errors[]`.
- Internationalisation through next-intl (English first; locale-aware number, currency and date formatting). Currency is formatted with `Intl.NumberFormat` using the record's currency, never the user's locale currency.
- Accessibility to WCAG 2.2 AA: keyboard navigable, focus states, aria labels, colour contrast checked.
- Responsive across all breakpoints:
  - mobile-first layouts;
  - the sidebar collapses to a Sheet on small screens;
  - data tables switch to card lists on mobile;
  - sticky action bars on document pages.
- Performance: route-level loading skeletons, streaming, image optimisation, and a bundle analysis check in CI.
- Testing:
  - Vitest and Testing Library for components;
  - Playwright E2E against the full Compose stack (the same golden path as backend E2E, via the UI);
  - Playwright accessibility checks with axe.

### 11.2 Key screens
- **Auth**: sign in or sign up (email, Google, Microsoft, Apple), 2FA, organization creation, invite acceptance.
- **Onboarding wizard**: business type (Invoicing vs Broker), organization details, branding and template pick, payment setup, import data, invite team.
- **Dashboard**: KPIs, renewals due, overdue invoices, quotes awaiting response, activity feed.
- **Clients**: list with filters and search, the client 360° page with a tabbed timeline, and a create/edit sheet.
- **Leads pipeline**: Kanban (P2).
- **Quotes**:
  - builder with live premium calculation and side-by-side insurer options;
  - template preview, send dialog (email, WhatsApp or SMS plus copy link);
  - status tracking timeline.
- **Billing**: invoices, debit and credit notes, receipts, payments, and payment allocation UI.
- **Policies**: list, detail (risks, documents, endorsements, billing, commission), the endorsement wizard, and the renewals board.
- **Commissions**: entries, the reconciliation workspace (statement upload → mapping → match queue), agent statements.
- **Remittances**: batch builder and advice PDF.
- **Claims** (P2).
- **Documents**, **Tasks**, the notification centre.
- **Reports** with charts, filters and export.
- **Settings**: organization, branches, users and roles, numbering, templates and branding, reminder rules, message templates, insurers and products, commission tables, jurisdiction pack, payment providers, integrations, billing/plan, audit log.
- **Public document page** (`/d/[token]`): branded and fast. It shows the rendered document, an Accept/Decline flow, Pay (M-Pesa phone prompt or card) and Download PDF, and works well on low-end mobile devices and slow networks.
- **Client portal** (P2).

### 11.3 UX principles
- Any core action is reachable in three clicks or fewer.
- ⌘K to search clients, policies and documents and to run commands.
- Inline editing where safe, autosaved drafts, undo for non-financial edits, and clear status badges everywhere.
- Empty states teach the user what to do next. Every list has bulk actions and saved filters.

---

## 12. Mobile (P2)
- Expo (managed workflow) with Expo Router and TypeScript, sharing `packages/api-client` and zod schemas.
- Auth uses the Better Auth Expo client, with secure token storage (`expo-secure-store`).
- Scope: dashboard, clients, quick quote, send document, policy lookup, renewals, tasks, notifications (push via Expo Notifications), document scan and upload (camera), record a payment.
- Offline: cache recent lists read-only, and queue simple mutations (notes, tasks).
- Builds and updates through EAS Build and EAS Update.

---

## 13. Observability and operations
- Structured JSON logs (structlog) shipped to the chosen log platform. Sentry covers the API, workers, auth and web.
- OpenTelemetry tracing across web → auth → API → worker (exporter configurable, off by default in dev).
- Prometheus `/metrics` on the API and workers: request latency, task durations, queue depth, payment webhook lag, messages sent and failed.
- Backups: nightly Postgres dumps plus point-in-time recovery in production, object-storage versioning, and backup restore drills documented in `docs/runbooks/`.
- A feature flag and kill switch per integration (for example, pause WhatsApp sends).
- Platform admin console (P2): tenants, plans, failed jobs, webhook replay, impersonation (audited and time-boxed).

---

## 14. Milestones

### Backend (complete and fully tested in Compose before the frontend starts)
| # | Milestone | Key acceptance criteria |
|---|---|---|
| **B0** | Scaffolding | Monorepo, `uv` project, FastAPI app factory, settings, logging, error handling (problem+json), health endpoints, Dockerfiles, `compose.yaml` and `compose.test.yaml` with all infrastructure services, Makefile, CI pipeline, pre-commit (ruff, mypy), `CLAUDE.md`, ADR-0001 (stack). `make test` runs green with a smoke test. |
| **B1** | Auth and tenancy | Auth service (Better Auth with email/password, Google, Microsoft, Apple, organization, 2FA, jwt, bearer, phoneNumber, magicLink). JWKS verification in the API. Tenant provisioning (hook plus lazy). RLS on all tables with tests. Permission registry and role matrix. Audit log. Idempotency store. Outbox. Org settings, branches and numbering. E2E: sign up → JWT → `/api/v1/me`. |
| **B2** | Core master data | Clients and contacts (with PII encryption), insurers, classes of business (risk schemas), products, commission rates, documents (presigned upload/download via MinIO), tasks. CSV/XLSX import for clients and insurers. Search. |
| **B3** | Calculation engine and jurisdictions | Pure `app/calc` with full table and property tests. Jurisdiction pack loader. `generic` pack plus `ke` pack (values marked [VERIFY]). Tax codes. Levy rules. |
| **B4** | Quotes, billing and templates | Generic and insurance quotes (options, versions, states). Invoices, debit and credit notes. Gapless numbering. Instalments. Document templates (8 at launch) with Jinja2 and Gotenberg rendering. Public links with tracking. Email sending via the adapter (Mailpit). Message templates. |
| **B5** | Payments and tax | Manual payments, allocation, receipts and ledger. Fake, Stripe and M-Pesa adapters with webhooks. Pay from a public link. Tax adapter interface plus the `kra_etims` sandbox implementation (behind a flag). Refunds. |
| **B6** | Policies and renewals | Quote → policy conversion. Policy risks. Endorsements (pro-rata and short-period) with debit and credit notes. Cancellations. Renewal generation. Reminder rules engine (email, SMS and WhatsApp adapters, quiet hours, dedupe). Notifications. |
| **B7** | Commissions, remittances and reports | Commission entries and splits, with WHT and VAT. Remittance batches and advice PDF. Insurer statement import and auto-matching. Dashboard and report endpoints with CSV/XLSX export, reconciled against the ledger. |
| **B8** | SaaS billing and hardening | Plans, entitlements, quotas, trials, Stripe Billing webhooks. Rate limiting. Schemathesis contract tests clean. Full E2E golden path. Performance check (p95 under 300 ms on core list and get endpoints with a seeded 50k-policy tenant). Security review checklist (ASVS L2). Data export and deletion endpoints. |

### Frontend and later
| # | Milestone |
|---|---|
| **F1** | Web foundation: Next.js, shadcn setup, theming, layout (sidebar, ⌘K), auth screens, onboarding, generated API client, error and toast handling, Playwright harness in Compose |
| **F2** | Clients, insurers and products, settings, documents, tasks |
| **F3** | Quote builder, billing documents, template picker and branding, send flow, public document page (accept and pay) |
| **F4** | Policies, endorsements, renewals board, reminders settings, notifications |
| **F5** | Commissions and reconciliation workspace, remittances, dashboard and reports, subscription and billing pages |
| **P2** | Leads pipeline, claims, client portal, recurring invoices, mobile app (Expo), admin console, duplicate merge |
| **P3** | Reinsurance (facultative), AI extraction and insights, SSO/SAML, custom portal domains, public API and webhooks for tenants, regulator returns, advanced e-signature, more jurisdiction packs |

---

## 15. Open decisions (product owner)
1. Launch country or countries. The default assumption is Kenya, with the `ke` pack and M-Pesa.
2. Product and brand name, domain, and the visual identity for templates.
3. Plan prices, limits and currency for subscriptions, and whether to accept M-Pesa for SaaS subscriptions.
4. Regional card/payment provider: Paystack, Flutterwave, or Stripe only.
5. SMS and WhatsApp: bundled credits or pass-through billing.
6. Hosting target. Containers make any option viable: a managed Postgres plus container platform (for example Fly.io, Render, Railway, AWS ECS or DigitalOcean), with data residency requirements to check per jurisdiction **[VERIFY]**.
7. Confirm Kenya levy rates, the tax treatment of commission, eTIMS integration type (OSCU/VSCU/API) and IRA remittance deadlines with a local accountant or compliance advisor before production.

---

## 16. Glossary
- **AMS**: Agency Management System.
- **Debit note**: the broker's bill to a client for premium (insurance equivalent of an invoice).
- **Credit note**: a document reducing an amount owed (refunds, cancellations, negative endorsements).
- **Endorsement**: a mid-term change to a policy.
- **Pro-rata / short-period**: methods to compute premium adjustments for partial periods.
- **Remittance**: paying collected premium over to the insurer.
- **Commissionable premium**: the portion of premium on which commission is computed (usually excluding levies and fees).
- **WHT**: withholding tax.
- **Facultative reinsurance**: reinsurance of an individual risk, negotiated per risk.
- **Treaty reinsurance**: reinsurance of a portfolio under an agreement; out of scope for now.
- **Cedent**: the insurer passing risk to a reinsurer.
- **Jurisdiction pack**: versioned configuration of country-specific tax, levy and compliance rules.
- **RLS**: Postgres Row-Level Security.
- **JWKS**: JSON Web Key Set, the public keys used to verify JWTs.
- **eTIMS**: Kenya Revenue Authority's Electronic Tax Invoice Management System.
- **STK Push**: M-Pesa prompt sent to a customer's phone to authorise a payment.
