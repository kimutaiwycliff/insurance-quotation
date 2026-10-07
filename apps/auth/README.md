# apps/auth: authentication service

Better Auth 1.7 on Hono (Node 24): email/password with verification, Google (optional), organizations and
invitations, TOTP 2FA, JWT/JWKS for the API, and a bearer plugin for mobile (ADR-0006).

```bash
pnpm install                  # pnpm 11 (pinned via packageManager; corepack enable)
pnpm run typecheck && pnpm test
pnpm run dev                  # needs AUTH_DATABASE_URL, BETTER_AUTH_SECRET (see the repo's .env.example)
```

- `src/auth.ts`: Better Auth configuration, roles, JWT claims, organization hooks → API `/internal/v1/*`.
- `src/migrate.ts`: creates and updates tables in schema `auth` (Compose service `auth-migrate`).
- Endpoints: `/api/auth/*` (Better Auth), `/health/live`, `/health/ready`.
