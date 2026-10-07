# ADR-0001: Technology stack

- Status: Accepted
- Date: 2026-10-07
- Supersedes: `docs/PROJECT_SPEC.md` §4.3 where they differ

## Context
The original spec listed technologies "latest stable at project start". A currency check on 2026-10-06
(`docs/SPEC_REVIEW.md` §5) found several were outdated or dead: MinIO was archived and its image removed;
PostgreSQL 18, Python 3.14, SQLAlchemy 2.1 and Valkey 9 were current; Next.js 16 renamed middleware to `proxy.ts`;
Stripe cannot serve Kenyan businesses.

## Decision
| Concern | Choice (pinned in lockfiles/images) |
|---|---|
| Language/runtime | Python 3.14, uv 0.12 |
| API | FastAPI 0.142, Pydantic 2.13, pydantic-settings 2.15 |
| Persistence | PostgreSQL 18.6, SQLAlchemy 2.1 (async, psycopg 3.3), Alembic 1.20 |
| Jobs | Procrastinate 3.10 (ADR-0004) |
| Cache/rate limiting | Valkey 9.1 (redis-py client) |
| Object storage | S3 API; RustFS 1.0 in dev/CI, AWS S3 or R2 in prod (ADR-0005) |
| PDF | Gotenberg 8.37, hardened flags |
| Dev email | Mailpit 1.31 |
| Quality | ruff, mypy 2.x `--strict`, import-linter, pytest 9, pytest-asyncio 1.x, hypothesis, time-machine, respx |
| Observability | structlog JSON logs, Prometheus metrics, Sentry; OpenTelemetry from M1 |
| Auth (M1) | Better Auth 1.7.x on Hono, Node 24 LTS |
| Web (W1) | Next.js 16.3 (`proxy.ts`), React 19, Tailwind 4, shadcn/ui CLI v4 with Radix primitives, TanStack Query 5, TanStack Table v8, zod 4, orval 8 client |
| Payments | Paystack first (tenant's own account), M‑Pesa Daraja as advanced; Stripe only if a non-Kenyan entity exists |
| CI | GitHub Actions with every action pinned by commit SHA; Trivy, pip-audit, oasdiff |

## Consequences
- New dependencies outside this list need an ADR amendment (CLAUDE.md rule 12).
- Dependabot proposes updates weekly; Next.js, React and Better Auth security releases are applied immediately.
- PG 19 (GA October 2026) is evaluated in 2027; Python 3.15 once Procrastinate, uvloop and psycopg support it.
