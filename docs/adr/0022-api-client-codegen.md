# ADR-0022: API client code generation

- Status: Accepted
- Date: 2026-10-07

## Decision
- orval 8 generates typed TanStack Query hooks and models from the committed `apps/api/openapi.json` into
  `apps/web/src/lib/api/generated` (`pnpm client`). The output is committed, and `make web-check` fails if
  it is stale.
- The custom mutator `src/lib/api/fetcher.ts` returns bodies directly (errors throw), so hooks are typed with
  success bodies only.
- API schema names must be unique across modules (e.g. `MessageTemplateOut`, `DocumentLinkOut`), otherwise
  generated names leak module paths.

## Consequences
- A separate `packages/api-client` and Turborepo come when a second consumer (mobile, R3) exists. Until then,
  each app keeps its own lockfile and pnpm 11 supply-chain policy.
- `If-Match` is passed per call (`ifMatch(version)`) by calling the generated request functions directly in
  update forms.
