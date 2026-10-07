"""Liveness and readiness probes.

* ``GET /health/live``: the process is up. Never touches dependencies.
* ``GET /health/ready``: Postgres, Valkey and object storage are reachable (each check time-boxed).
"""

import asyncio
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from app.platform.resources import Resources, get_resources

router = APIRouter(prefix="/health", tags=["health"])
logger = structlog.get_logger(__name__)


class CheckStatus(StrEnum):
    OK = "ok"
    FAIL = "fail"


class LiveResponse(BaseModel):
    status: CheckStatus


class ReadyResponse(BaseModel):
    status: CheckStatus
    checks: dict[str, CheckStatus]


async def _run_check(
    name: str, check: Callable[[], Awaitable[object]], limit_seconds: float
) -> CheckStatus:
    try:
        async with asyncio.timeout(limit_seconds):
            await check()
    except Exception as exc:
        logger.warning("readiness_check_failed", check=name, error=type(exc).__name__)
        return CheckStatus.FAIL
    return CheckStatus.OK


@router.get("/live", operation_id="health_live")
async def live() -> LiveResponse:
    return LiveResponse(status=CheckStatus.OK)


@router.get(
    "/ready",
    operation_id="health_ready",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadyResponse}},
)
async def ready(
    response: Response, resources: Annotated[Resources, Depends(get_resources)]
) -> ReadyResponse:
    timeout = resources.settings.readiness_timeout_seconds
    checks = {
        "database": resources.ping_database,
        "valkey": resources.ping_valkey,
        "storage": resources.storage.ping,
    }
    results = await asyncio.gather(
        *(_run_check(name, check, timeout) for name, check in checks.items())
    )
    outcome = dict(zip(checks, results, strict=True))
    overall = CheckStatus.OK if all(r is CheckStatus.OK for r in results) else CheckStatus.FAIL
    if overall is CheckStatus.FAIL:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyResponse(status=overall, checks=outcome)
