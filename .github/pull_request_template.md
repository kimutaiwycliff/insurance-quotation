## What and why

<!-- One or two sentences. Link the milestone (e.g. M1) and any ADR. -->

## Definition of done (docs/IMPLEMENTATION_PLAN.md §3.1)

- [ ] Migration(s) added and reversible where practical; RLS policies explicit for new tenant tables
- [ ] Unit + integration tests; tenancy and permission tests for new tenant-scoped endpoints
- [ ] `make check` and `make test` pass locally
- [ ] `openapi.json` regenerated (`make openapi`); breaking changes justified
- [ ] Docs updated (module README, ADR, `.env.example`, CHANGELOG)
- [ ] No secrets, tokens or PII in code, fixtures or logs
- [ ] Money uses `Decimal`; issued financial records are never mutated

## How it was verified

<!-- Commands run, screenshots for UI, sandbox evidence for integrations. -->
