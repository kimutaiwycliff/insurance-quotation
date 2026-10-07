"""HTTP-level unit tests: health probes, problem+json errors, request IDs, OpenAPI."""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from app.core.errors import PROBLEM_CONTENT_TYPE, NotFoundError, register_error_handlers
from app.core.middleware import REQUEST_ID_HEADER, RequestContextMiddleware
from app.main import create_app


class TestHealth:
    async def test_live_is_ok_without_dependencies(self, unit_client: httpx.AsyncClient) -> None:
        response = await unit_client.get("/health/live")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    async def test_ready_reports_each_unreachable_dependency(
        self, unit_client: httpx.AsyncClient
    ) -> None:
        response = await unit_client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {
            "status": "fail",
            "checks": {"database": "fail", "valkey": "fail", "storage": "fail"},
        }


class _Payload(BaseModel):
    qty: int


@pytest.fixture
async def error_client() -> AsyncIterator[httpx.AsyncClient]:
    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(RequestContextMiddleware)

    @app.get("/missing")
    async def missing() -> None:
        raise NotFoundError("Client 42 does not exist")

    @app.post("/validate")
    async def validate(payload: _Payload) -> _Payload:
        return payload

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret internals")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


class TestProblemDetails:
    async def test_domain_error_maps_to_problem(self, error_client: httpx.AsyncClient) -> None:
        response = await error_client.get("/missing")
        assert response.status_code == 404
        assert response.headers["content-type"] == PROBLEM_CONTENT_TYPE
        body = response.json()
        assert body["code"] == "not_found"
        assert body["detail"] == "Client 42 does not exist"
        assert body["instance"] == "/missing"
        assert body["request_id"] == response.headers[REQUEST_ID_HEADER]

    async def test_validation_error_lists_fields(self, error_client: httpx.AsyncClient) -> None:
        response = await error_client.post("/validate", json={"qty": "many"})
        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "validation_error"
        assert body["errors"][0]["field"] == "body.qty"

    async def test_unknown_route_is_problem_json(self, error_client: httpx.AsyncClient) -> None:
        response = await error_client.get("/nope")
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    async def test_unexpected_error_hides_internals(self, error_client: httpx.AsyncClient) -> None:
        response = await error_client.get("/boom")
        assert response.status_code == 500
        assert response.json()["code"] == "internal_error"
        assert "secret internals" not in response.text


class TestRequestId:
    async def test_generates_request_id(self, unit_client: httpx.AsyncClient) -> None:
        response = await unit_client.get("/health/live")
        assert len(response.headers[REQUEST_ID_HEADER]) >= 32

    async def test_propagates_valid_incoming_request_id(
        self, unit_client: httpx.AsyncClient
    ) -> None:
        response = await unit_client.get(
            "/health/live", headers={REQUEST_ID_HEADER: "edge-req-12345678"}
        )
        assert response.headers[REQUEST_ID_HEADER] == "edge-req-12345678"

    async def test_replaces_malicious_request_id(self, unit_client: httpx.AsyncClient) -> None:
        response = await unit_client.get(
            "/health/live", headers={REQUEST_ID_HEADER: "bad id\nwith injection"}
        )
        assert response.headers[REQUEST_ID_HEADER] != "bad id\nwith injection"


class TestOpenApi:
    def test_operation_ids_are_explicit(self) -> None:
        schema = create_app().openapi()
        assert schema["openapi"].startswith("3.1")
        operation_ids = {
            op["operationId"] for path in schema["paths"].values() for op in path.values()
        }
        assert {"health_live", "health_ready"} <= operation_ids
