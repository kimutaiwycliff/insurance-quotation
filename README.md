# BrokerOS (working name)

Client, quote, policy, renewal and commission management for **Kenyan insurance agents**, plus a standalone
quotation & invoicing product for small businesses.

> Status: **M0 (foundations) complete.** See [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) for the
> roadmap and [`CHANGELOG.md`](CHANGELOG.md) for what has shipped.

## Quick start

Requirements: Docker (with Compose v2), [uv](https://docs.astral.sh/uv/) ≥ 0.12 for local tooling, GNU make.

```bash
cp .env.example .env        # optional; compose.yaml has development defaults
make up                     # builds and starts postgres, valkey, storage, mailpit, gotenberg, auth, api, worker
curl localhost:8000/health/ready
make test                   # full backend suite inside Compose (the definition of done)
```

| Service | URL (local) |
|---|---|
| API + OpenAPI docs | http://localhost:8000/docs |
| Auth service (Better Auth) | http://localhost:3001/api/auth (JWKS: `/api/auth/jwks`) |
| Mailpit (dev email) | http://localhost:8025 |
| Object storage console (RustFS) | http://localhost:9001 |
| Postgres | `localhost:55432` (non-standard to avoid clashing with a local Postgres) |

Run `make help` for all targets.

## Documentation
- [`CLAUDE.md`](CLAUDE.md): working rules for engineers and coding agents
- [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md): milestones, definition of done, test strategy
- [`docs/SPEC_REVIEW.md`](docs/SPEC_REVIEW.md): verified Kenyan regulatory facts and spec corrections
- [`docs/PROJECT_SPEC.md`](docs/PROJECT_SPEC.md): original product specification
- [`docs/adr/`](docs/adr/README.md): architecture decision records
- [`SECURITY.md`](SECURITY.md) · [`CONTRIBUTING.md`](CONTRIBUTING.md)
