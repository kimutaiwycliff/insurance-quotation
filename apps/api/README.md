# apps/api: core API and workers

FastAPI service plus Procrastinate workers, sharing one image (targets `api`, `worker`, `test`).

```bash
uv sync --frozen                                   # local tooling and IDE support
uv run pytest tests/unit                           # unit tests (no Docker)
uv run uvicorn app.main:create_app --factory --reload   # needs the Compose infra and env vars
```

- Settings: `app/core/config.py` (all from environment variables; see the repo's `.env.example`).
- Migrations: `alembic upgrade head` with `MIGRATIONS_DATABASE_URL` (the `app_owner` role).
- Worker: `procrastinate --app=app.workers.app.app worker`.
- OpenAPI: `python -m scripts.export_openapi > openapi.json` (committed; CI checks it is current).
