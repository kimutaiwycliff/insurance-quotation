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

## Amendments
- 2026-10-08 (R2.1–R2.2): **response values that grow are published as `x-extensible-enum`**:
  - covers permission keys, billing document kinds and statuses (`app/core/schema.py: ExtensibleEnum`);
  - the generated TypeScript types them as `string`, and the UI must handle a value it does not know (show it
    as-is);
  - request fields keep closed enums;
  - adding such a value is not a breaking change in the `oasdiff` CI check; removing or renaming one still is.

## Consequences
- A separate `packages/api-client` and Turborepo come when a second consumer (mobile, R3) exists. Until then,
  each app keeps its own lockfile and pnpm 11 supply-chain policy.
- `If-Match` is passed per call (`ifMatch(version)`) by calling the generated request functions directly in
  update forms.
