"""RFC 9457 ``application/problem+json`` error handling.

Domain code raises subclasses of :class:`AppError`; this module is the single place where exceptions are
mapped to HTTP problem responses. Every problem carries a stable machine-readable ``code``.
"""

from http import HTTPStatus
from typing import Any, ClassVar

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_CONTENT_TYPE = "application/problem+json"
PROBLEM_TYPE_BASE = "https://docs.brokeros.app/problems/"

logger = structlog.get_logger(__name__)


class FieldError(BaseModel):
    field: str = Field(description="Dotted path of the offending field, e.g. `body.lines.0.qty`")
    message: str
    code: str


class Problem(BaseModel):
    type: str
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    code: str
    request_id: str | None = None
    errors: list[FieldError] | None = None


class AppError(Exception):
    """Base class for expected, client-visible errors."""

    status: ClassVar[HTTPStatus] = HTTPStatus.BAD_REQUEST
    code: ClassVar[str] = "bad_request"
    title: ClassVar[str] = "Bad request"

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(detail or self.title)
        self.detail = detail


class NotFoundError(AppError):
    status = HTTPStatus.NOT_FOUND
    code = "not_found"
    title = "Resource not found"


class ConflictError(AppError):
    status = HTTPStatus.CONFLICT
    code = "conflict"
    title = "Conflict"


class PermissionDeniedError(AppError):
    status = HTTPStatus.FORBIDDEN
    code = "permission_denied"
    title = "Permission denied"


def _request_id(request: Request) -> str | None:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) else None


def problem_response(
    request: Request,
    *,
    status: int,
    code: str,
    title: str,
    detail: str | None = None,
    errors: list[FieldError] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    problem = Problem(
        type=f"{PROBLEM_TYPE_BASE}{code}",
        title=title,
        status=status,
        detail=detail,
        instance=request.url.path,
        code=code,
        request_id=_request_id(request),
        errors=errors,
    )
    return JSONResponse(
        problem.model_dump(exclude_none=True),
        status_code=int(status),
        media_type=PROBLEM_CONTENT_TYPE,
        headers=headers,
    )


# Handlers are registered per exception type, so each receives exactly that type.
async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    return problem_response(
        request, status=exc.status, code=exc.code, title=exc.title, detail=exc.detail
    )


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        FieldError(
            field=".".join(str(part) for part in err.get("loc", ())),
            message=str(err.get("msg", "Invalid value")),
            code=str(err.get("type", "invalid")),
        )
        for err in exc.errors()
    ]
    return problem_response(
        request,
        status=HTTPStatus.UNPROCESSABLE_CONTENT,
        code="validation_error",
        title="Request validation failed",
        errors=errors,
    )


async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    status = HTTPStatus(exc.status_code)
    detail = exc.detail if isinstance(exc.detail, str) and exc.detail != status.phrase else None
    return problem_response(
        request,
        status=status,
        code=status.name.lower(),
        title=status.phrase,
        detail=detail,
        headers=dict(exc.headers) if exc.headers else None,
    )


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", exc_type=type(exc).__name__, exc_info=exc)
    return problem_response(
        request,
        status=HTTPStatus.INTERNAL_SERVER_ERROR,
        code="internal_error",
        title="Internal server error",
    )


def register_error_handlers(app: FastAPI) -> None:
    handlers: dict[Any, Any] = {
        AppError: _handle_app_error,
        RequestValidationError: _handle_validation_error,
        StarletteHTTPException: _handle_http_exception,
        Exception: _handle_unexpected,
    }
    for exc_type, handler in handlers.items():
        app.add_exception_handler(exc_type, handler)
