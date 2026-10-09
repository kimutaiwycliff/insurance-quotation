# ADR-0025: Plans, entitlements and subscription billing

- Status: Accepted
- Date: 2026-10-09

## Context
Prices were approved on 2026-10-08 (docs/PRICING.md): Free, Agent, Agency (5 users plus extra users) and
Business (3 users); yearly at 10 months; a 30-day trial; a founding offer of 50% off for 12 months for the
first 100 paying tenants. Cards are on hold, so we bill by M-Pesa (ADR-0015). We need one place that
decides what a tenant may do, enforced by the API (the web only hides what the API refuses).

## Decision
- **Plans are code, not data** (`app/modules/subscriptions/plans.py`). Each plan has features
  (`insurance`, `comparison_quotes`, `commission`, `book_import`, `client_reminders`, `branding`, `etims`,
  `team`), limits (`clients`, `documents_per_month`, `seats`) and prices. Jurisdiction rule 4 does not apply:
  these are our commercial terms, not statutory rules. Changing a price is a code change with a CHANGELOG
  entry; existing paid periods are kept.
- **One subscription row per tenant** (`app.subscriptions`, forced RLS), created with the tenant: a 30-day
  **Agency** trial (so teams can try roles), then Free unless they pay.
- **Status is computed, not stored**: trialing → active (paid period) → past_due (7 days of grace, full
  access) → read_only (reads, exports and paying still work; any other write is refused with 402
  `subscription_inactive`). Free never expires.
- **Entitlements ride on the Principal** (`plan`, `features`, `read_only`), resolved once per request with
  the membership. Routers use `require_feature(...)`; services call `check_limit(...)` at the point of
  creation (client, issued document, seat). Refusals are 402 problem+json: `plan_feature`, `plan_limit`.
  Service tokens and platform jobs get `features={"*"}`.
- **Seats are checked in the auth service** before an invitation is created or accepted
  (`POST /internal/v1/seats/check`), not when memberships sync, so lazy provisioning never fails.
- **Billing is a prepaid M-Pesa STK Push to the platform's own shortcode** (`PLATFORM_MPESA_*`). Nothing
  renews automatically. A payment activates only after STK Query confirms (same rule as tenant payments).
  The period runs from the later of today and the current period end. This is our own revenue, not client
  or tenant funds, so rule 5 holds.
- **Founding members**: the first 100 tenants to pay keep 50% off for 12 months from their first payment.
  The count is a SECURITY DEFINER function, so it can count across tenants without exposing rows.

## Consequences
- One code path for every gate; the web reads `me.features` to hide navigation and shows plan pages
  instead of errors.
- No card vault, no dunning engine: renewal is a prompt the owner accepts. Renewal reminders, referrals
  and receipts for our own billing follow in R2.5b.
- Plan changes mid-period take effect at payment and do not prorate; downgrades never delete data, they
  only hide features and stop new records over the limit.
