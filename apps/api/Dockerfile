# syntax=docker/dockerfile:1.7
# Multi-stage image shared by the API, the job worker, migrations and the test runner.
# Targets: api | worker | test

ARG PYTHON_IMAGE=python:3.14-slim-bookworm

FROM astral/uv:0.12.23 AS uv

# ---------------------------------------------------------------- base
FROM ${PYTHON_IMAGE} AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PYTHONPATH=/app \
    PATH="/opt/venv/bin:${PATH}"
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /app --no-create-home app
WORKDIR /app

# ---------------------------------------------------------------- dependencies (no project code: cache-friendly)
FROM base AS deps
COPY --from=uv /uv /bin/uv
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

FROM deps AS test-deps
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

# ---------------------------------------------------------------- runtime
FROM base AS runtime
COPY --from=deps /opt/venv /opt/venv
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app scripts ./scripts
COPY --chown=app:app app ./app
USER app

FROM runtime AS api
EXPOSE 8000
# Proxy headers are trusted only from FORWARDED_ALLOW_IPS (uvicorn reads it from the environment).
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--no-server-header", "--timeout-graceful-shutdown", "20"]

FROM runtime AS worker
CMD ["procrastinate", "--app=app.workers.app.app", "worker"]

# ---------------------------------------------------------------- test runner
FROM base AS test
COPY --from=test-deps /opt/venv /opt/venv
COPY --chown=app:app . .
# pytest and coverage write caches/data into the working directory (runtime images stay read-only).
RUN chown app:app /app
USER app
CMD ["pytest"]
