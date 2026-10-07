# PROJECT_SPEC.md — Critical Review & Verification

> Reviewed: 2026-10-06 · Subject: `PROJECT_SPEC.md` (974 lines, "BrokerOS")
> Companion: [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md)
>
> Method: full read of the spec; independent engineering review; four parallel research passes (Kenyan regulation &
> tax, payment & messaging providers, technology-stack currency, market/competitors) against primary sources where
> reachable (Kenya Law consolidated Acts, KRA, IRA, Safaricom, Stripe, Paystack, Meta, PyPI/npm/GitHub/Docker Hub
> APIs). Confidence: **H**igh / **M**edium / **L**ow.
>
> **Not legal or tax advice.** Every regulatory value must still be signed off by a Kenyan tax adviser and insurance
> lawyer before seeding (spec §15.7 already requires this). Open items are listed in §7.

---

## 1. Verdict

The spec is **well above average** and most of it should be kept (see §8). It has, however, five classes of problems
that would cause expensive rework if building started today:

| # | Class | Severity | Examples |
|---|---|---|---|
| A | Kenyan regulatory/domain facts wrong or missing | 🔴 Critical | Levies, stamp duty, VAT and WHT modelled incorrectly; eTIMS applied to the wrong documents and treated as optional; s.156 premium-handling and "no premium, no cover" not modelled |
| B | Payment architecture not viable as written | 🔴 Critical | Stripe unavailable to Kenyan businesses; Daraja callbacks unsigned; per-tenant Daraja go-live breaks "self-serve in an afternoon"; platform must never hold funds (CBK licensing) |
| C | Internal engineering contradictions / latent bugs | 🟠 High | RLS policy throws instead of filtering; child tables lack `tenant_id`; FKs bypass RLS; state machines conflate orthogonal states; `NUMERIC(20,2)` vs 0-dp currencies; test-isolation design can't work |
| D | Stale or dead technology | 🟠 High | MinIO archived and image removed; PG 17→18, Python 3.13→3.14, Redis 7→Valkey 9, Next "latest"→16.3 (`proxy.ts`); Trivy-action supply-chain incident |
| E | Scope & sequencing risk | 🟠 High | ~20 modules and 8 backend milestones before any UI or user feedback; B1 alone has 7 sign-in methods; small Kenyan broker TAM; a self-serve competitor already exists |

---

## 2. Regulatory & domain findings (Kenya)

### 2.1 Verified Kenya-pack values (replaces the §6.6 seed list)

| Item | Spec says | Verified rule | Conf. | Source |
|---|---|---|---|---|
| Training levy | ~0.2%, "most general classes" | **0.2% of gross direct premium, general business only** (medical included; life/long-term excluded). Charged to policyholder, collected by insurer. Rate set by Gazette order → configurable. | H basis, M‑H rate | Insurance Act s.197B; Regs r.56–57 |
| PCF levy | ~0.25%, general classes | **0.25% charged to the policyholder on all classes incl. post‑2005 life**; excludes reinsurance, superannuation, pre‑2005 life. The insurer pays a separate 0.25% itself — **not** on the client debit note. | H | PCF Regs LN 86/2010 reg 9 |
| Stamp duty | flat per policy, some classes | **KES 40** per policy (accident, sickness, property and "any other" — motor, fire, liability, medical); **life KES 7.50 per KES 10,000 sum assured**; **marine** KES 5 or per‑10,000 bands by voyage/time; single-journey accident KES 5; **cover notes not stamped**. Insurer liable, passed on. | H | Stamp Duty Act Sched. item 27 |
| VAT on premium | generally exempt | **Exempt.** | H | VAT Act 1st Sched. Pt II para 2 |
| VAT on broker/agent commission | "per KRA rules"; formula adds VAT | **Exempt** (2020 deletion of the exemption declared unconstitutional — AKI v KRA 2021; confirmed KPMG Mar‑2026). Asset-management commissions, consultancy and loss-adjusting are **16%**. | H | KPMG 2026; EY 2022 |
| WHT on commission | pack, resident/non-resident | **Withheld by the insurer: 5% resident brokers, 10% other residents (agents), 20% non-residents.** Not final tax for residents. Brokers receive **net** commission. | H | ITA s.35, 3rd Sched. Head B |
| Remittance deadline | "per IRA rules" | **No statutory "remit within N days" for brokers.** Agents authorised to collect remit **"immediately upon receipt"** (r.42). Brokers: separate **trust client account**, may net own commission, remittance statement, annual auditor certificate, KES 3m guarantee/bond, PI cover, **half-yearly outstanding-premium return with a >60‑day bucket (INS 153‑1)**, 31‑Dec premiums-due statement within 2 months. | H texts | s.156; Regs r.39–43 |
| "No premium, no cover" | not modelled | Insurer may not assume risk until premium is received (or bank guarantee/deposit). r.43 exceptions: medical instalments, declaration policies (75%), WIBA/CIT provisional, marine (15 days), bonds/CAR staggered. **Policy activation must be gated on this.** | H | s.156; r.41, r.43 |
| 2019 s.156 amendment | — | Forbade intermediaries receiving premium; **nullified by the High Court** (AIBK v CS Treasury, 29‑Jul‑2021). Appeal status **unverified**; Kenya Law still prints the 2019 text. → collection mode must be switchable. | M | [2021] KEHC 451 |
| Insurance Premium Levy 1% | — | Paid by the insurer to IRA; **not** a client line. | H | s.197A |
| Excise on fees | — | **20% excise on "other fees"** charged by Insurance-Act licensees; premium and premium-based commission excluded → broker flat admin/service fees **likely** attract 20% (interpretation — confirm). | M | Excise Duty Act |
| Short-period table | from pack | **No national table**; insurer-specific. Per insurer/product, pack only as fallback. | M | Insurer wordings |
| eTIMS scope | mandatory for VAT-registered; submit debit notes | **Mandatory for every person in business, VAT-registered or not** (TPA s.23A). Expenses without an eTIMS invoice are non-deductible; KRA cross-validates returns. **Premium debit notes: not eTIMS** (industry guidance via AKI; not a listed statutory exemption — M). **Brokers must issue eTIMS invoices to insurers for their own commission and fees (exempt-coded).** | H / M | TPA s.23A; eTIMS Regs 2024 |
| eTIMS integration | OSCU/VSCU or API | A SaaS integrating OSCU/VSCU for customers **must be a KRA-certified third-party integrator** (dev → sandbox → vetting → certification; tax compliance certificate, ≥3 qualified technical staff, architecture docs). **Each tenant registers its own PIN + branch + device.** Sandbox `etims-sbx.kra.go.ke`. Fees and timeline unverified. | H process, L timeline | KRA eTIMS S2S |
| ODPC registration | "[VERIFY]" | **Mandatory** for insurance intermediaries (financial services is a Third-Schedule purpose, so the small-entity exemption doesn't apply) **and for us as processor.** Renew every 2 years. | H | LN 265/2021 |
| Data localisation | "[VERIFY]" | **No blanket localisation for private insurance data.** **Health data** (medical members, DOB, conditions) is sensitive: cross-border transfer needs **data-subject consent + safeguards**. Breach: controller→ODPC **72 h**, processor→controller **48 h**. DSR deadlines: access 7 d; rectification/erasure/restriction/objection 14 d; portability 30 d. | H | DPA s.43, 48–50; LN 263/2021 |
| IRA licensing of the platform | not addressed | Defensible as a tech provider **only while the licensed broker/agent is the visible party.** If the platform canvasses the public, compares insurers under its own brand, or earns per-policy commission or lead fees → risk of being an **unlicensed intermediary**. Draft Intermediaries Regs 2025 pending; IRA sandbox "BimaBox". | M | Insurance Act s.2 |
| E-acceptance | simple acceptance | Valid evidence under KICA; **advanced** e-signatures equal handwritten (BLAA 2020). Simple acceptance fine for quotes. | M | KICA; BLAA 2020 |
| Our own SaaS tax | not addressed | Kenyan entity: **16% VAT** on subscriptions (above KES 5m) and **eTIMS invoices for our own subscription billing** (regardless of VAT status). Non-resident entity: 16% VAT on digital supplies (no threshold) + **SEP tax ≈3% of gross** (DST abolished Dec‑2024). PSP fees carry 16% VAT (FA 2026). | H | VAT Act s.8; ITA s.12E |

### 2.2 Consequences for the calculation engine (§6.2–6.4)
1. Levy rules need: class/business-line filters (`general` / `long_term`), effective dates, basis, rate, min/max, **`charged_to ∈ {client, insurer}`** (only client-charged levies reach the debit note), refundable flag, commissionable flag.
2. Stamp-duty rule types: `flat`, `per_unit_of_sum_insured` (life, marine bands), conditional tiers (marine), `exempt_for_document_kind` (cover notes).
3. Commission (§6.3) becomes `gross → WHT withheld by insurer → net received`, plus WHT-certificate reconciliation. Keep `vat_on_commission` in the generic engine; the KE pack sets it to `exempt`.
4. WHT rate depends on the tenant's `intermediary_type` (broker 5%, agent 10%, non-resident 20%).
5. Fees need a tax code that can carry 20% excise (pending confirmation).
6. Short-period tables are insurer/product data with a pack fallback.

### 2.3 Consequences for the domain model
- **Collection mode** per policy (default per insurer): `broker_collects` | `insurer_direct` (client pays the insurer's paybill; broker invoices commission only). Both first-class.
- **Activation gating**: `pending → active` requires premium-received evidence (insurer confirmation, broker remittance, or an r.43 exception record).
- **Premium trust (client-money) ledger account**, separate from operating cash; net-of-commission remittance statements; outstanding-premium ageing with the 60-day flag; INS 153‑1-style half-yearly return; 31‑Dec premiums-due statement.
- **New document type: commission/fee invoice to insurer** — the broker's eTIMS-transmitted supply. The spec has no such document.
- **For the Invoicing tier, every Kenyan tenant's invoice must be eTIMS-transmitted.** eTIMS is therefore on the critical path for selling in Kenya, not an optional flag. Until we are a certified integrator, support **manual eTIMS reference capture** (tenant issues via the KRA portal or eTIMS Lite and records the CU invoice number and QR) as a compliant stopgap.

---

## 3. Payments & messaging findings

| # | Finding | Conf. | Correction |
|---|---|---|---|
| P1 | **Stripe doesn't support Kenyan merchant accounts** ("Extended network"; redirects to Paystack). A Kenyan company can't use Stripe Billing or be a Connect platform without a foreign entity. | H | **Paystack** is the primary card/M‑Pesa provider for KE tenants and for our own KE SaaS billing. Stripe Connect (hosted onboarding, direct charges — not OAuth or raw keys) only for a global tier **if** a non-Kenyan entity exists (decision D1). |
| P2 | Paystack KE: cards, M‑Pesa, Airtel Money, Apple Pay, Pesalink; 2.9% local; webhooks HMAC‑SHA512 with **the merchant's secret key**; **recurring charges are card-only.** | H | Store each tenant's secret key encrypted (needed to verify their webhooks). M‑Pesa subscription renewals: our own scheduler + STK reminders, or M‑Pesa Ratiba (commercial agreement). |
| P3 | **Daraja callbacks are not signed** (STK, C2B). Daraja 3.0 live since Nov‑2025, same base URLs. | H | Per-tenant, per-request unguessable callback path (no query string); Safaricom IP allowlist as defence in depth (ranges unverified); match `CheckoutRequestID` + amount + phone to a request we created; **mandatory server-side confirmation (STK Query / Transaction Status / C2B Pull) before marking paid**; idempotency on `MpesaReceiptNumber`. |
| P4 | `AccountReference` ≤ **12 chars**, `TransactionDesc` ≤ **13**. | M‑H | `INV-2026-00001` (14 chars) won't fit. Add a short `payment_reference` (≤12 alphanumerics) per billing document for STK/C2B; keep the formal number separate. |
| P5 | Till vs Paybill differ (`CustomerBuyGoodsOnline`: head-office shortcode + till as `PartyB`). | H | Tenant M‑Pesa config: `transaction_type`, `business_shortcode`, `party_b`, `passkey`, `consumer_key/secret`, optional `initiator_name` + `security_credential`. |
| P6 | **Per-tenant Daraja go-live takes days to weeks** (Org Portal admin, operator, OTP; C2B validation needs a separate request). | M | Fast path via aggregators where the tenant is merchant of record (tenant's own Paystack first); direct Daraja as "advanced" with a guided go-live checklist. |
| P7 | **CBK/NPS Act**: collecting on behalf of others and settling onward requires PSP authorisation; draft NPS Bill 2026 in consultation. | M‑H | **Invariant: the platform never holds, pools or settles tenant or client funds.** Paystack split/subaccount models only after legal review. |
| P8 | C2B payers mistype account numbers. | H | Unmatched-payments queue, fuzzy matching, daily Pull/statement reconciliation. |
| P9 | Africa's Talking: per-tenant sender ID takes 2–5+ days (separate transactional and promotional IDs on Safaricom); DLR callbacks unsigned; promotional SMS needs opt-in + STOP (KICA regs, DPA s.37; ODPC has fined). | M | Platform transactional sender ID as default; per-recipient suppression list; secret callback path. |
| P10 | WhatsApp Cloud API: per-message pricing since Jul‑2025; **from 1‑Oct‑2026 service and in-window utility messages are charged** after 1,000 free per number per month (~$0.004 utility, ~$0.0225 marketing); multi-tenant = **Tech Provider + Embedded Signup**, each tenant on its own WABA; `X-Hub-Signature-256`. | M‑H | Meta verification + App Review as long-lead; per-message cost model. |
| P11 | Email: Gmail permanently rejects non-compliant mail (since Nov‑2025); RFC 8058 one-click unsubscribe; Apple MPP makes opens meaningless; SES Tenant Management (Aug‑2025). | H | "Viewed" = JS beacon on a real page render, never an email open. Per-tenant DKIM/DMARC with a shared fallback domain. Recommend **Amazon SES (tenant management)**, Postmark as alternative. |
| P12 | Flutterwave: CBK licence unverified; v3 webhook is a static shared secret. | M | Deprioritise. |

---

## 4. Engineering findings

### 4.1 Tenancy & RLS
1. **The RLS policy as written throws rather than filters.** `current_setting('app.tenant_id')::uuid` raises when the setting is absent, contradicting §10.3 #4 ("returns zero rows"). Use `tenant_id = (SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid)`; the sub-select is also evaluated once per query, not per row.
2. **Child tables lack `tenant_id`** in §6.1 (`QuoteLine`, `QuoteOption`, `ClientContact`, `PolicyRisk`, `Endorsement`, `BillingLine`, `InstalmentSchedule`, `PaymentAllocation`, `CommissionSplit`, `RemittanceItem`, `LinkEvent`, `InsurerStatementLine`, `LedgerEntry`), contradicting rule §0.2.6. Every tenant-owned row carries `tenant_id`.
3. **FK checks bypass RLS**, so a row can reference another tenant's parent. Use **composite FKs** `(tenant_id, parent_id) → parent(tenant_id, id)` with `UNIQUE (tenant_id, id)`.
4. `FORCE ROW LEVEL SECURITY` on every tenant table.
5. **Catalog guard test**: fail CI if any table in schema `app` is neither tenant-scoped (RLS enabled + forced + policy + composite FKs) nor on an explicit global allowlist. Alembic autogenerate does not see policies; this test is the safety net.
6. Mixed global/tenant tables (`ClassOfBusiness`, `MessageTemplate`) need split policies: read `tenant_id IS NULL OR = current`; write only own rows.
7. **Webhooks have no tenant at ingress**, but verification secrets are per tenant. Use per-connection endpoints `/webhooks/{provider}/{connection_public_id}`; resolve, verify, then store with `tenant_id`.
8. Cross-tenant scans (reminders, expiry) use a narrow `app_scanner` role restricted to specific views of `(tenant_id, id, due_at)`, then enqueue per-tenant jobs that run as `app_user`. Avoid broad `BYPASSRLS`.

### 4.2 State machines
1. **Billing conflates three dimensions** in `issued → sent → viewed → partially_paid → paid`; an invoice paid by C2B without being sent can't be represented. Split into `status` (`draft | issued | void`), `delivery_status` (`not_sent | sent | delivered | viewed`, tracking only), `payment_status` (`unpaid | partially_paid | paid | overpaid`, derived from allocations) and derived `is_overdue` (tenant timezone). Same for Quote: `viewed` is tracking.
2. **Quote revision vs immutability**: a revision is a **new row** (`parent_quote_id`); the old one becomes **`superseded`** (state missing); its links are revoked or redirect.
3. Once transmitted to eTIMS, a document can only be corrected by credit note.
4. `policy_number` is often unknown at conversion → nullable until bound; add cover-note support; activation gated (§2.3).
5. Partial refunds: `Refund` records with derived refund status, not `succeeded → refunded`.

### 4.3 Money & calculations
1. **`NUMERIC(20,2)` breaks 0‑dp (UGX, RWF, BIF) and 3‑dp currencies.** Store `NUMERIC(20,4)` and round to the ISO 4217 minor unit from a currency table.
2. Rounding: "round lines, total = sum of rounded lines" conflicts with tax on totals → pack setting `tax_rounding: per_line | per_document` (KE = per line, as eTIMS computes per item).
3. Premium formula ambiguities to resolve with **accountant-signed golden examples**: loadings/discounts as % or amount, and on what base; minimum premium is applied twice; which premium is the levy basis.
4. **Pro-rata contradiction**: `remaining_days / total_days` vs "actual/365" give different results for 366-day periods. Pick per pack (recommend `remaining_days / period_days`) and test leap years.
5. Multi-currency ledger: journals balance **per currency**; FX gain/loss unspecified → v1 requires payment currency = document currency; reports convert at issue-date rate.
6. Commission split base (gross vs net of WHT) → tenant setting, default net.

### 4.4 API & persistence
- **Idempotency store in Postgres, same transaction as the effect**, keyed `(tenant_id, principal_id, method+route, key)`; same key with a different body hash → 422; in flight → 409.
- UUIDv7: PG 18 `uuidv7()` / Python 3.14 `uuid.uuid7()`; generate app-side.
- Audit log append-only by `REVOKE UPDATE, DELETE` from `app_user`; optional per-tenant hash chain.
- PII encryption: `key_id` with each ciphertext, KMS envelope encryption in prod, separate HMAC key for lookup hashes, normalise before hashing.
- Rate limiting is unspecified → Valkey token bucket: per IP (public), per tenant (API keys), per phone (STK).
- `/metrics` must not be publicly routable.
- **Async API + sync Celery "with one driver"** forces duplicate service code or `asyncio.run()` per task (see §5).

### 4.5 Documents & public links
1. **XSS**: the public page embeds API-rendered HTML, and **Jinja2 autoescape is off unless configured**, while tenant-entered notes and names flow in. Require autoescape, no `|safe` on tenant data, a **sandboxed iframe** (no `allow-scripts`) and a strict CSP. No tenant-authored Jinja; if ever allowed, use `SandboxedEnvironment`.
2. **Gotenberg SSRF**: `--chromium-deny-private-ips=true`, restrictive `--chromium-allow-list`, `--chromium-disable-javascript=true`, inline assets, internal network only.
3. **False "viewed" events** from WhatsApp/email unfurlers and scanners: count only JS-beacon views and filter bot UAs.

### 4.6 Time
"Today" (overdue, expiry, quiet hours, reminder offsets) must be computed in the **tenant's timezone**; the spec never says which zone defines a day.

### 4.7 Jobs
Outbox dispatch via Beat "every few seconds" is a poor fit (use a dispatcher with `FOR UPDATE SKIP LOCKED` + `LISTEN/NOTIFY`). The Redis broker has no native DLQ (spec promises one), and `visibility_timeout` vs ETA causes duplicate runs. Beat must be a strict singleton.

### 4.8 Testing design
- Per-test rollback can't coexist with real `app_user` RLS connections, the 50-way concurrent numbering test, job execution, and `pytest -n auto` on one DB. → **Per-xdist-worker database cloned from a migrated template**; rollback fixture by default; `@pytest.mark.committing` tests truncate.
- schemathesis 4 has a new API (`schemathesis.openapi.from_asgi`, `schemathesis.toml`).
- The coverage gate on only `service.py` + `core/` lets routers, adapters and calc slip → whole-`app/` floor plus **≥95% on `app/calc`**.

### 4.9 Auth
- **B1 is overloaded** (email/password, Google, Microsoft, Apple, passkey, phone OTP, magic link, 2FA). Apple needs a paid developer account; phone OTP needs live SMS. Stage them.
- **Role source of truth**: Better Auth stores membership + role **key**; the API owns role→permission mapping and custom roles; `perms_version` claim invalidates caches.
- **No built-in "2FA-verified" claim in Better Auth (verified).** Enforce "2FA enabled" for privileged roles plus a custom session field via hook + `definePayload`, or step-up in the auth service.
- **Revocation lag** of 15-minute JWTs → mirror membership changes via org hooks and check membership per request (cache ≤60 s).
- **Server components need a JWT**: Next server gets it from `/api/auth/token` (cached per session) and calls FastAPI; the browser never holds the API JWT.
- Better Auth 1.7: set `baseURL`, `trustedOrigins`, `iss`, `aud` explicitly; use `organizationHooks.afterCreateOrganization`; keep all `@better-auth/*` on one version; several 2026 critical advisories → subscribe.
- Internal provisioning call: short-lived signed JWT (`aud=internal`) plus network isolation, not a static token.

---

## 5. Technology-stack corrections

| Component | Spec | Current (2026‑10‑06) | Action |
|---|---|---|---|
| **MinIO** | `minio/minio` | **Repo archived Feb‑2026; image removed; no CVE fixes** | **RustFS** (`rustfs/rustfs:1.0.x`, Apache‑2.0) for dev/CI, Garage as fallback; prod AWS S3 or R2. Plain S3 API (`endpoint_url`, path-style); bucket setup via boto3, not `mc`. |
| PostgreSQL | 17 | **18.6** (`uuidv7()`, async I/O) | Use 18 + SCRAM; pgcrypto optional. |
| Python | 3.13 | **3.14.8** (`uuid.uuid7()`); 3.15 final 2026‑10‑09 | 3.14. |
| SQLAlchemy | 2.x | **2.1.3** | Target 2.1. |
| Redis | 7 / Valkey | Redis 8 (AGPL/RSAL/SSPL), **Valkey 9.1** (BSD‑3) | **Valkey 9.** |
| Celery | 5 | 5.6.3 | See recommendation below. |
| Better Auth | — | **1.7.7**; passkey/sso/expo are separate `@better-auth/*` packages; CLI `npx auth@latest` | Pin; pre-create `auth` schema + `search_path`. |
| Next.js | "latest" | **16.3.x** LTS; `middleware.ts` → **`proxy.ts`**; Turbopack default; monthly security releases; 2025–26 CVEs (middleware bypass, React2Shell RCE, rewrite SSRF) | Pin 16.3.x. `proxy.ts` is UX routing only, never the security boundary. Static rewrite destinations. No tenant data in `"use cache"`. |
| TypeScript | strict | **7.0** (Go-native); typescript-eslint needs 7.1 API | Pin 6.x for lint tooling until 7.1. |
| shadcn/ui | — | CLI v4; **Base UI default**, Radix still available; Recharts v3 | Choose the primitive explicitly. |
| TanStack Table | — | v9 (new API); shadcn examples on v8 | Pin v8. |
| zod | — | 4.x | Use 4. |
| API codegen | hey-api or orval | hey-api 0.99 (0.x, breaking minors); **orval 8.40** | **orval 8** (stable semver; React Query + zod + MSW). |
| pnpm / Node | — | pnpm 12, **Node 24 LTS** | Use them. |
| mypy | strict | 2.4 (new defaults) | mypy 2.x strict as gate. |
| Testing | freezegun/time-machine | pytest 9, pytest-asyncio 1.x, **time-machine 3.5**, schemathesis 4.29 | time-machine; asyncio 1.x idioms. |
| CI | Trivy | **trivy-action compromise (CVE‑2026‑33634, Mar‑2026)** | **SHA-pin every action**, least-privilege `permissions:`, OIDC; add **oasdiff**. |
| Gotenberg | 8 | 8.37 | Hardening flags (§4.5). |

**Job-runner recommendation (needs approval — changes the listed stack):** replace Celery+Beat with **Procrastinate**
(Postgres-backed, async-native, transactional enqueue, built-in periodic tasks). It removes three problems at once:
the async/sync code split; separate outbox machinery for job dispatch (enqueuing inside the business transaction *is*
the outbox); and the Redis broker's DLQ/visibility-timeout caveats. Valkey stays for cache and rate limits. If not
approved: Celery 5.6 with a dedicated outbox dispatcher, `acks_late`, idempotent tasks, a `failed_jobs` table and a
singleton Beat.

---

## 6. Product, scope & market

### 6.1 Market-claim corrections (§1.3)
| Claim | Verified |
|---|---|
| SAIBA and Simson as separate vendors | **Same company** (Simson Softwares, India); has KE/TZ/UG clients. |
| TBW as a regional emerging-market system | **Canadian** (CSSI). Remove. |
| InsurOPS (Kenya) as an implementation-style ERP | **Wrong: self-serve, public pricing US$149/499 per month, 30-day no-card trial, Kenya office.** Closest direct competitor. |
| AgencyZoom ~$149 | Verified (Vertafore-owned). |
| GloveBox ~$499 | Disputed: from ~$150; branded-app tier quote-based. GloveBoxCRM = former Better Agency. |
| QQCatalyst "Bain-owned" | Vertafore owned by **Roper** since 2020. |
| Marrikel | Renamed **Re Square**. |
| Zoho Invoice free; FreshBooks $23 | Verified. **Zoho Books Kenya with eTIMS from KES 849–999/mo** is the SME price floor. |
| Market size | 67 insurers, **181 licensed brokers**, 23 bancassurance intermediaries (2026); penetration **2.63%** (FY2025); GWP KES 466.6bn. Agent count unverified. **Lami** offers free multi-insurer quoting to agents. |

### 6.2 Implications
1. **The Kenyan broker-firm market is a few hundred firms.** Volume must come from agents, small agencies and the Invoicing tier, plus UG/TZ/RW — a strong case to **ship the Invoicing tier first**.
2. "Self-serve + public pricing" is no longer unique. Defensible differentiators: KES pricing paid by M‑Pesa; eTIMS-ready flows; **s.156-aware premium handling** (trust account, activation gating, INS 153‑1 return) as a compliance moat; best client-facing documents; lower entry price.
3. Price anchors: Invoicing ~KES 1,000–2,500/user/mo; agent ~KES 3,000–6,500; broker firm ~KES 10,000–30,000. A 14-day trial is weaker than InsurOps' 30 days → a free capped tier or a 30-day trial.
4. Stay **white-label** (tenant is the visible party) to avoid IRA intermediary licensing.

### 6.3 Scope & sequencing
P1 (~20 modules) plus "no UI until B8" means months of engineering with zero user feedback and no revenue.
**Recommendation (needs approval; changes rule §0.2.1):** keep "API complete and tested before its UI" **per
vertical slice**. Release **Invoicing first (R1)**, then **Broker MVP (R2)**, then **Broker Pro (R3)**. Launch with
**3 templates**, not 8.

---

## 7. Decisions & sign-offs required

| # | Decision / sign-off | Owner | Needed before |
|---|---|---|---|
| **D1** | Legal entity & domicile (Kenyan only, or + foreign entity for Stripe/global tier) | Product owner + accountant | M4 |
| **D2** | Approve release re-sequencing (R1 Invoicing → R2 Broker; backend-first per slice) | Product owner | M0 |
| D3 | Job runner: Procrastinate vs Celery | Tech lead | M1 |
| **D4** | Tax adviser sign-off on KE pack values and golden calculation examples | Accountant | M5 / M7 |
| **D5** | Lawyer opinion: s.156 appeal status, collection modes, not-an-intermediary positioning, Paystack splits, e-acceptance wording | Lawyer | R2 |
| D6 | Hosting region & health-data residency stance | Product owner + DPO | M0 |
| D7 | Brand, name, domain | Product owner | M2 |
| D8 | Prices/limits in KES; trial model | Product owner | M4 |
| D9 | Regional card provider (recommend Paystack) | Product owner | M4 |
| D10 | SMS/WhatsApp billing model | Product owner | R3 |
| D11 | Radix vs Base UI; orval vs hey-api; TanStack Table v8 vs v9 | Tech lead | W1 |

**Long-lead external items — start now:** (1) **KRA eTIMS third-party integrator certification**; (2) ODPC registration + DPIA for health data; (3) Paystack business account; (4) Meta business verification → Tech Provider → App Review; (5) Africa's Talking account + platform sender ID; (6) Daraja developer account + one pilot go-live; (7) sending domains with SPF/DKIM/DMARC + SES production access; (8) Apple Developer account (only if Apple sign-in/iOS is in scope); (9) recruit 3–5 broker/agent and 5–10 SME pilot customers.

**Unverified items to close with professionals:** Gazette order for the 0.2% training levy; s.156 appeal status; the
legal instrument behind "no eTIMS on premium debit notes"; excise/VAT on broker flat fees; eTIMS certification fees and
timeline; IRA rules on electronic policy documents; IRA licensed-agent count; Safaricom callback IP ranges.

---

## 8. Keep unchanged (strengths)

Modular monolith with service/event boundaries · RLS tenancy with dedicated roles · `Decimal`/`NUMERIC`, money as
strings · immutable financial documents corrected by credit notes · effective-dated, versioned jurisdiction packs ·
gapless numbering with `SELECT … FOR UPDATE` at issue time · double-entry ledger with balance tests · idempotency keys ·
optimistic concurrency · RFC 9457 errors · cursor pagination · adapters with fakes and `@pytest.mark.sandbox` tests ·
pure, property-tested calc engine · webhook "verify → store → 200 → async process → replayable" · hashed public-link
tokens (SHA‑256 is right for 256-bit random tokens) · same HTML for web view and PDF · Compose-based definition of
done · ADR discipline · OWASP ASVS L2 target.
