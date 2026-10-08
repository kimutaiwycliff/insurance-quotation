"""Shared fixtures.

Unit tests (tests/unit) need no infrastructure. Integration tests (tests/integration) need the Compose stack
and only run when ENVIRONMENT=test, which compose.test.yaml sets.
"""

import os
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from hypothesis import settings as hypothesis_settings

from app.core.config import Environment, Settings
from app.main import create_app

INFRA_AVAILABLE = os.environ.get("ENVIRONMENT") == Environment.TEST.value

# Property tests check correctness, not speed: no per-example deadline (CI machines can be slow and shared).
hypothesis_settings.register_profile("default", deadline=None)
hypothesis_settings.load_profile("default")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skip_integration = pytest.mark.skip(reason="needs Compose infrastructure (run `make test`)")
    for item in items:
        if "tests/integration" in str(item.path):
            item.add_marker(pytest.mark.integration)
            if not INFRA_AVAILABLE:
                item.add_marker(skip_integration)


@pytest.fixture
def unit_settings() -> Settings:
    """Settings pointing at nothing reachable, for tests that must not touch infrastructure."""
    return Settings(
        environment=Environment.TEST,
        log_json=False,
        metrics_enabled=False,
        database_url="postgresql+psycopg://nobody:nobody@127.0.0.1:1/none",  # type: ignore[arg-type]
        valkey_url="redis://127.0.0.1:1/0",  # type: ignore[arg-type]
        s3_endpoint_url="http://127.0.0.1:1",
        readiness_timeout_seconds=0.5,
    )


async def _client_for(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client,
    ):
        yield client


@pytest.fixture
async def unit_client(unit_settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    async for client in _client_for(create_app(unit_settings)):
        yield client


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """Client wired to the real Compose services (integration tests only)."""
    async for c in _client_for(create_app(Settings())):
        yield c
