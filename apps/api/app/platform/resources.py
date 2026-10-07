"""Process-wide resources created in the app lifespan and shared by request handlers."""

from dataclasses import dataclass
from typing import Self

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core import db
from app.core.config import Settings
from app.integrations.storage.s3 import S3Storage


@dataclass(slots=True)
class Resources:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    valkey: Redis
    storage: S3Storage

    @classmethod
    def create(cls, settings: Settings) -> Self:
        engine = db.create_engine(settings)
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
        await self.valkey.aclose()
        await self.engine.dispose()
