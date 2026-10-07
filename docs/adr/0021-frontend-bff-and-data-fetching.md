# ADR-0021: Frontend data fetching & BFF

- Status: Accepted
- Date: 2026-10-07

## Decision
- **The browser talks only to the web app**, apart from presigned storage URLs.
  - `/api/auth/*` is a same-origin proxy to the auth service, so Better Auth cookies are first-party.
  - `/bff/api/v1/*` forwards to the API. It runs as route handlers, with destinations fixed by server
    configuration (`AUTH_INTERNAL_URL`, `API_INTERNAL_URL`) and read at runtime, so one image serves every
    environment.
- **The API token never reaches the browser.**
  - The BFF and server components mint a short-lived JWT from the auth service with the session cookie, and
    cache it for 30 s, keyed by a hash of the cookie header.
  - An `org_epoch` cookie, changed on agency create or switch, invalidates that cache.
  - Only `/api/v1/*` paths are forwarded, with an allow-list of request headers.
- **Server components** fetch with `serverApi()`. **Client components** use the generated TanStack Query hooks,
  whose fetcher targets the BFF, adds an `Idempotency-Key` to every POST and throws `ApiError` (RFC 9457).
  Forms map problem field errors to fields; anything else becomes a toast in plain words.
- **Updates** send `If-Match: W/"<version>"` built from the resource's `version`.
- **`proxy.ts` only redirects** signed-out visitors (UX). Pages and the BFF check the session server-side.
- **Document previews** render API HTML in `<iframe sandbox="">` (no scripts) via `srcDoc`.
- **Accessibility:**
  - WCAG 2.2 AA, checked by axe in the Playwright golden path on desktop and a 390 px viewport;
  - visible maize focus ring, reduced-motion respected, native selects on forms (best on phones);
  - Atkinson Hyperlegible body type.

## Consequences
- IDs use `crypto.getRandomValues` (`randomId()`), not `crypto.randomUUID()`, which is missing outside
  secure contexts.
- Sandboxed iframes are excluded from axe scans: axe cannot run inside them. Their content is covered by the
  template tests (ADR-0014).
