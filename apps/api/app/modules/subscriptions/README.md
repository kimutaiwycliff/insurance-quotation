# subscriptions

Our own plans and billing (docs/PRICING.md, ADR-0025).

- `plans.py`: plans, features, limits, prices, trial and founding-offer constants. Pure data and `price()`.
- `service.py`:
  - `start_trial` (called by tenancy when a tenant is provisioned);
  - `entitlements` (plan, features, limits, read_only), which tenancy puts on the Principal;
  - `check_feature`, `check_limit` (402 `plan_feature` / `plan_limit`);
  - `checkout` (STK Push to the platform shortcode), `check_payment` (STK Query; activates the period),
    `resolve_callback`.
- `router.py`:
  - `/api/v1/subscription`: current plan with usage, `/plans`, `/checkout`, `/payments`, `/payments/{id}`.
    These work while the account is read-only.
  - `/webhooks/mpesa-platform/{secret}/stk`: Safaricom's callback (secret path, optional IP allow-list).
- Tables: `subscriptions` (one per tenant) and `subscription_payments`; both have forced RLS. The
  SECURITY DEFINER functions are `app.founding_members_count()` and `app.resolve_subscription_payment(text)`.

Other modules use it only through `service.py`: `Feature`, `Limit`, `check_feature`, `check_limit`,
`entitlements`, `start_trial`. Route gating is `app.platform.deps.require_feature`.

Status by date: trialing until `trial_ends_at`; active until `current_period_end`; past_due for
`GRACE_DAYS` (full access); then read_only. Free never lapses.

Config: `PLATFORM_MPESA_ENVIRONMENT` (`simulator` locally; refused in production), shortcode, keys,
passkey and `PLATFORM_MPESA_CALLBACK_SECRET`; see `.env.example`.
