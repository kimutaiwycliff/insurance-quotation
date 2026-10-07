# Contributing

1. Read [`CLAUDE.md`](CLAUDE.md). Its rules apply to humans and agents alike.
2. Branch from `main`. Use Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`).
3. Keep pull requests small and focused, and fill in the PR template's definition-of-done checklist.
4. Before pushing: `make check` (fast, no Docker), then `make test` (full suite in Compose).
5. Changing the API? Run `make openapi` and commit `apps/api/openapi.json`. Breaking changes need justification and usually a new API version.
6. Significant decisions get an ADR in `docs/adr/` (Context / Decision / Consequences).
7. Optional local hooks: `uvx pre-commit install`.
