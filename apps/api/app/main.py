"""FastAPI application factory.

Run with ``fastapi run app/main.py`` or ``uvicorn app.main:app --factory``-style via the module-level ``app``.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import REQUEST_ID_HEADER, RequestContextMiddleware
from app.core.telemetry import configure_sentry
from app.platform import health
from app.platform.resources import Resources

API_V1_PREFIX = "/api/v1"
# Contract version of the public API (not the build): bump deliberately, checked by oasdiff in CI.
API_VERSION = "1.0.0"

logger = structlog.get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    configure_sentry(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resources = Resources.create(settings)
        await resources.open()
        app.state.resources = resources
        logger.info("startup", environment=settings.environment.value, release=settings.release)
        try:
            yield
        finally:
            await resources.close()
            logger.info("shutdown")

    app = FastAPI(
        title="BrokerOS API",
        version=API_VERSION,
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    register_error_handlers(app)

    # Middleware order: the last added runs first (outermost).
    if settings.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allowed_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "Idempotency-Key",
                "If-Match",
                REQUEST_ID_HEADER,
            ],
            expose_headers=[REQUEST_ID_HEADER, "ETag", "Retry-After"],
        )
    app.add_middleware(RequestContextMiddleware)

    app.include_router(health.router)
    app.include_router(APIRouter(prefix=API_V1_PREFIX))  # feature routers are mounted here from M1

    if settings.metrics_enabled:
        # Must only be reachable on the internal network; the ingress never routes /metrics.
        app.mount("/metrics", make_asgi_app())

    return app
