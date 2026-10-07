"""Database engine and session management.

The API connects as ``app_user`` (not the table owner) so Postgres Row-Level Security is always enforced.
Each request runs in one transaction whose tenant is set with ``set_config('app.tenant_id', ..., true)``
(the transaction-local equivalent of ``SET LOCAL``); see ADR-0003.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        str(settings.database_url),
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,
        connect_args={
            "options": f"-c statement_timeout={settings.database_statement_timeout_ms}",
            "application_name": settings.service_name,
        },
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@asynccontextmanager
async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """One transaction per unit of work: commit on success, roll back on error."""
    async with factory() as session, session.begin():
        yield session


async def set_tenant_context(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Scope the current transaction to ``tenant_id``. Must be called inside ``session.begin()``.

    The setting is transaction-local, so it can never leak to the next user of a pooled connection.
    """
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


@asynccontextmanager
async def tenant_scope(
    factory: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID
) -> AsyncIterator[AsyncSession]:
    """A transaction scoped to one tenant (jobs and internal endpoints)."""
    async with factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        yield session


async def ping(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
