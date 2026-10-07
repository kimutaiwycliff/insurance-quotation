"""Request context middleware: request IDs, structured access logs and HTTP metrics.

Implemented as pure ASGI middleware (not ``BaseHTTPMiddleware``) so it does not buffer streaming responses
and preserves contextvars for the downstream handler.
"""

import re
import time
import uuid

import structlog
from prometheus_client import Counter, Histogram
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")

HTTP_REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "route", "status_class"])
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0, 2.5, 5.0),
)

access_logger = structlog.get_logger("access")

# Paths that are polled frequently and would drown the access log.
_QUIET_PATHS = frozenset({"/health/live", "/health/ready", "/metrics"})


def _incoming_request_id(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == b"x-request-id":
            candidate = value.decode("latin-1")
            return candidate if _VALID_REQUEST_ID.match(candidate) else None
    return None


def _route_template(scope: Scope) -> str:
    """Low-cardinality route label: the matched path template, never the raw path."""
    route = scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "unmatched"


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope) or str(uuid.uuid7())
        scope.setdefault("state", {})["request_id"] = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        status_code = 500
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed = time.perf_counter() - started
            method = scope["method"]
            route = _route_template(scope)
            HTTP_REQUESTS.labels(method, route, f"{status_code // 100}xx").inc()
            HTTP_LATENCY.labels(method, route).observe(elapsed)
            if scope["path"] not in _QUIET_PATHS:
                access_logger.info(
                    "http_request",
                    method=method,
                    route=route,
                    status=status_code,
                    duration_ms=round(elapsed * 1000, 2),
                )
            structlog.contextvars.clear_contextvars()
