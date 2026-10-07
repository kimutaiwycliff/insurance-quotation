"""Integration fixtures: an API client whose tokens are signed by an in-memory key, and test organizations.

Isolation strategy: every test creates its own organizations (random ids), so tests commit for real and still
never see each other's data; RLS is what keeps them apart, which is exactly what we want to exercise.
"""

from collections.abc import AsyncIterator, Callable

import httpx
import psycopg
import pytest

from app.core.config import Settings
from app.main import create_app
from app.workers.app import libpq_dsn
from tests.support import Org, SigningKey, StaticKeys, new_id, service_claims


@pytest.fixture(scope="session")
def signing_key() -> SigningKey:
    return SigningKey()


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def make_api(
    signing_key: SigningKey,
) -> Callable[..., AsyncIterator[httpx.AsyncClient]]:
    async def factory(**overrides: object) -> AsyncIterator[httpx.AsyncClient]:
        app = create_app(Settings(**overrides), key_source=StaticKeys(signing_key))  # type: ignore[arg-type]
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver"
            ) as client,
        ):
            yield client

    return factory


@pytest.fixture
async def api(
    make_api: Callable[..., AsyncIterator[httpx.AsyncClient]],
) -> AsyncIterator[httpx.AsyncClient]:
    async for client in make_api(rate_limit_enabled=False):
        yield client


@pytest.fixture
def org(signing_key: SigningKey) -> Org:
    return Org(key=signing_key)


@pytest.fixture
def other_org(signing_key: SigningKey) -> Org:
    return Org(key=signing_key)


@pytest.fixture
def service_headers(signing_key: SigningKey) -> dict[str, str]:
    return {"Authorization": f"Bearer {signing_key.sign(service_claims())}"}


async def provision(api: httpx.AsyncClient, org: Org) -> None:
    """Provision through the API's lazy path (first request with the owner's token)."""
    response = await api.get("/api/v1/me", headers=org.headers())
    assert response.status_code == 200, response.text


@pytest.fixture
async def ready_org(api: httpx.AsyncClient, org: Org) -> Org:
    await provision(api, org)
    return org


@pytest.fixture
async def app_user_conn(settings: Settings) -> AsyncIterator[psycopg.AsyncConnection]:
    """A raw connection as the API role (subject to RLS), autocommit off."""
    conn = await psycopg.AsyncConnection.connect(libpq_dsn(str(settings.database_url)))
    async with conn:
        yield conn


@pytest.fixture
async def owner_conn(settings: Settings) -> AsyncIterator[psycopg.AsyncConnection]:
    assert settings.migrations_database_url is not None
    conn = await psycopg.AsyncConnection.connect(
        libpq_dsn(str(settings.migrations_database_url)), autocommit=True
    )
    async with conn:
        yield conn


__all__ = ["new_id", "provision"]
