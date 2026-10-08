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
from app.core.security import KeySource
from app.core.telemetry import configure_sentry
from app.modules.clients import router as clients_router
from app.modules.dashboard import router as dashboard_router
from app.modules.documents import router as documents_router
from app.modules.leads import router as leads_router
from app.modules.messaging import router as messaging_router
from app.modules.notifications import router as notifications_router
from app.modules.numbering import router as numbering_router
from app.modules.public_links import router as public_links_router
from app.modules.rendering import router as rendering_router
from app.modules.tasks import router as tasks_router
from app.modules.tenancy import internal as tenancy_internal
from app.modules.tenancy import router as tenancy_router
from app.modules.tenancy.service import resolve_principal
from app.platform import audit, health
from app.platform.resources import Resources

API_V1_PREFIX = "/api/v1"
# Contract version of the public API (not the build): bump deliberately, checked by oasdiff in CI.
API_VERSION = "1.0.0"

logger = structlog.get_logger(__name__)


def api_v1_router() -> APIRouter:
    router = APIRouter(prefix=API_V1_PREFIX)
    router.include_router(tenancy_router.router)
    router.include_router(numbering_router.router)
    router.include_router(documents_router.router)
    router.include_router(rendering_router.router)
    router.include_router(public_links_router.router)
    router.include_router(messaging_router.router)
    router.include_router(clients_router.router)
    router.include_router(leads_router.router)
    router.include_router(tasks_router.router)
    router.include_router(dashboard_router.router)
    router.include_router(notifications_router.router)
    router.include_router(messaging_router.public_router)
    # Anonymous routes (token-scoped, per-IP rate limited); no require_permission by design.
    router.include_router(public_links_router.public_router)
    router.include_router(audit.router)
    return router


def create_app(settings: Settings | None = None, *, key_source: KeySource | None = None) -> FastAPI:
    """Build the app. ``key_source`` replaces the JWKS fetcher (tests sign tokens with their own keys)."""
    settings = settings or get_settings()
    configure_logging(settings)
    configure_sentry(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resources = Resources.create(settings, key_source=key_source)
        resources.principal_resolver = resolve_principal
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
    app.include_router(api_v1_router())
    # Service-to-service routes; the ingress must never route /internal/* (see docs/architecture/auth.md).
    app.include_router(tenancy_internal.router)

    if settings.metrics_enabled:
        # Must only be reachable on the internal network; the ingress never routes /metrics.
        app.mount("/metrics", make_asgi_app())

    return app
