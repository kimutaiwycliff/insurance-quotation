"""Process-wide resources created in the app lifespan and shared by request handlers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Self

import httpx
from fastapi import Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core import db
from app.core.config import Settings
from app.core.security import JwksCache, KeySource, TokenVerifier
from app.integrations.storage.s3 import S3Storage

if TYPE_CHECKING:
    from app.platform.deps import PrincipalResolver


@dataclass(slots=True)
class Resources:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    valkey: Redis
    storage: S3Storage
    http: httpx.AsyncClient
    token_verifier: TokenVerifier
    # Set by app.main (the tenancy module implements it); core and platform never import modules.
    principal_resolver: PrincipalResolver | None = field(default=None)

    @classmethod
    def create(cls, settings: Settings, *, key_source: KeySource | None = None) -> Self:
        engine = db.create_engine(settings)
        http = httpx.AsyncClient(follow_redirects=False)
        keys = key_source or JwksCache(
            settings.auth_jwks_url,
            http,
            cache_seconds=settings.auth_jwks_cache_seconds,
            min_refetch_seconds=settings.auth_jwks_min_refetch_seconds,
        )
        return cls(
            settings=settings,
            engine=engine,
            session_factory=db.create_session_factory(engine),
            valkey=Redis.from_url(
                str(settings.valkey_url),
                socket_connect_timeout=2,
                socket_timeout=2,
                health_check_interval=30,
            ),
            storage=S3Storage(settings),
            http=http,
            token_verifier=TokenVerifier(settings, keys),
        )

    async def open(self) -> None:
        """Open long-lived clients. Connections themselves are established lazily."""
        await self.storage.open()

    async def ping_database(self) -> None:
        await db.ping(self.engine)

    async def ping_valkey(self) -> None:
        await self.valkey.ping()

    async def close(self) -> None:
        await self.storage.close()
        await self.http.aclose()
        await self.valkey.aclose()
        await self.engine.dispose()


def get_resources(request: Request) -> Resources:
    resources = request.app.state.resources
    if not isinstance(resources, Resources):
        raise TypeError("app.state.resources is not initialised; is the lifespan running?")
    return resources
