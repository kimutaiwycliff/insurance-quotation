# ADR-0007: Roles & permissions

- Status: Accepted
- Date: 2026-10-07

## Context
Spec §2.2 lists broker-oriented roles. Plan Amendment A1 makes Kenyan insurance agents the customer: a solo agent,
or an agency with a few agents and office staff.

## Decision
1. **Better Auth stores the role key; the API owns what it means.** `app/core/permissions.py` has the permission
   registry (`Perm`, strings like `branch:manage`) and the role → permission map. Better Auth only uses roles to
   decide who may manage members (owner and admin).
2. **Default roles (agent-first):** `owner` (agency owner), `admin` (office manager), `agent`, `accounts`,
   `assistant` (customer service), `viewer`. `broker` and `csr` from the spec map to `agent` and `assistant`.
   When the auth service reports several roles, the highest one wins. Better Auth's generic `member` maps to
   `agent`, and unknown roles grant only `viewer` rights.
3. **Every `/api/v1` endpoint declares one permission** with `require_permission(...)`. A unit test fails if
   a route doesn't. A generated role × endpoint matrix test checks allowed and denied combinations.
   `/me` is the only route open to every member.
4. **MFA policy: optional by default** (product decision, 2026-10-07). Every user can enrol TOTP, and the token
   carries `mfa_enrolled`. Nobody is forced: `MFA_ENFORCED_ROLES` is empty. Setting it (e.g. `owner,accounts`)
   gives those roles `403 mfa_required` until they enrol. `/me` stays available and reports `mfa_required` so the
   UI can prompt.
5. Record-level scoping ("own" vs "all", e.g. an agent's own clients) is applied in service queries as each
   module arrives (R1).

## Consequences
- New modules add permissions to the registry and to the role map in the same change.
- Custom roles (R3) will store additional role → permission rows per tenant. The registry stays the source of
  valid permission strings.
- Optional 2FA keeps onboarding friction low for solo agents. A per-tenant "require 2FA for my team" setting
  can be added later on top of the same check.
