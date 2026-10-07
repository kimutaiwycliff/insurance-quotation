# apps/web: web app (Next.js 16.3, BFF)

Sign-in/up, 2FA, onboarding, the app shell and settings (agency profile, team, documents & brand with live
preview, document numbers, security). See ADR-0021 (BFF) and ADR-0022 (API client).

```bash
pnpm install                 # pnpm 11 (corepack); CI=true for non-interactive installs
pnpm dev                     # needs AUTH_INTERNAL_URL and API_INTERNAL_URL (defaults: localhost:3001 / :8000)
pnpm lint && pnpm typecheck && pnpm test
pnpm client                  # regenerate src/lib/api/generated from ../api/openapi.json
make e2e-web                 # (repo root) Playwright + axe golden path in Compose, desktop and 390 px
```

- `src/app/(auth)`: auth screens (Better Auth client through the `/api/auth` proxy).
- `src/app/onboarding`: create agency → details → brand.
- `src/app/(app)`: shell and settings. `src/app/bff`: API proxy that attaches the token server-side.
- Design tokens are in `src/app/globals.css`. The agency's stamp seal is `components/brand/seal.tsx`.
- Copy lives in `messages/en.json` (next-intl; sentence case, plain verbs).
