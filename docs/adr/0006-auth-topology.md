# ADR-0006: Authentication topology & JWT flow

- Status: Accepted
- Date: 2026-10-07

## Context
The product needs email/password with verification, Google sign-in, organizations with invitations, TOTP 2FA,
and later mobile clients. The API is Python; Better Auth (TypeScript) is the most complete option (ADR-0001).

## Decision
1. **Standalone auth service** (`apps/auth`): Better Auth 1.7 on Hono, Node 24. It runs the email/password
   (verification required), Google (when configured), organization, twoFactor (TOTP), jwt and bearer plugins.
   Its tables live in schema `auth`, owned by `auth_owner`, which the API cannot write. Migrations run as a
   one-shot Compose service (`auth-migrate`, programmatic `getMigrations`, unsafe changes refused).
2. **Access tokens.** EdDSA (Ed25519) JWTs with a 15-minute lifetime, from `GET /api/auth/token`; JWKS at
   `/api/auth/jwks`. Claims: `sub`, `email`, `name`, `mfa_enrolled`, and for the active organization `org_id`,
   `org_role`, `org_name`, `org_slug`. `iss` and `aud` (`brokeros-api`) are pinned and checked by the API.
3. **API verification** (`app/core/security.py`). JWKS is cached for 10 min. An unknown `kid` triggers one
   refetch, rate-limited to every 30 s. Only asymmetric algorithms from an allow-list are accepted. `exp`, `nbf`,
   `iat`, `iss`, `aud` and `sub` are required, with 30 s leeway. PyJWT[crypto] was added as a small dependency
   (amends ADR-0001).
4. **Membership mirror instead of trusting `org_role`.** Organization hooks (create, add, accept invitation,
   role change, remove) call the API's `/internal/v1/*`. The API reads the mirror **on every request**, inside
   the request's RLS transaction, so a removal or role change applies on the next request, not in 15 minutes.
   This replaces the planned 60 s cache: the lookup is one indexed row in a transaction we open anyway.
5. **Lazy provisioning.** If a hook was missed, the first request with an unknown `org_id` creates the tenant
   and the membership from the verified claims. Both paths are idempotent and safe under concurrency.
6. **Service tokens.** Hooks authenticate with a 60 s JWT signed by the same JWKS (`aud` = `brokeros-internal`,
   `sub` = `service:auth`). Access tokens cannot call internal routes, and service tokens cannot call tenant
   routes. `/internal/*` is not in the OpenAPI document and must never be routed by the public ingress.
7. **Web (W1).** Next.js rewrites `/api/auth/*` to this service (same-origin cookies). The BFF obtains the JWT
   server-side; the browser never holds the API token. Mobile uses the bearer plugin.

## Consequences
- The auth service is a second runtime (Node) to patch; security releases of Better Auth are applied
  immediately (ADR-0001).
- Microsoft, passkeys and magic links are deferred to W-phase/R2; Apple and phone OTP to mobile (P2).
- Key rotation: see `docs/runbooks/rotate-auth-keys.md`.
