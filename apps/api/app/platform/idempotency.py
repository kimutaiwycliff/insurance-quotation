"""Idempotency keys for mutating requests (ADR-0011).

Clients send ``Idempotency-Key: <uuid or other unique string>`` on POSTs. The key is claimed with an
``INSERT ... ON CONFLICT DO NOTHING`` **in the request's own transaction**, then the response is stored in the
same row before commit. Consequences:

* the effect and its stored response commit (or roll back) together;
* a concurrent retry blocks on the unique index until the first request finishes, then replays its response
  (no "in progress" error and no double effect);
* a failed request stores nothing (its transaction rolled back), so the client may retry with the same key;
* the same key with a different method, path or body → 422 ``idempotency_key_reused``.

Usage in an endpoint::

    if (replay := await idem.replay()) is not None:
        return replay
    ...
    return await idem.respond(201, BranchOut.model_validate(branch))
"""

import hashlib
import re
from datetime import timedelta
from typing import Annotated, Any

from fastapi import Depends, Header, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, IdempotencyKeyReusedError
from app.platform.deps import ResourcesDep, TenantContext
from app.platform.models import IdempotencyKey

REPLAY_HEADER = "Idempotent-Replayed"
_VALID_KEY = re.compile(r"^[\x21-\x7e]{8,255}$")  # printable ASCII, no spaces


class InvalidIdempotencyKeyError(AppError):
    code = "invalid_idempotency_key"
    title = "Idempotency-Key must be 8-255 printable ASCII characters"


class Idempotency:
    def __init__(
        self, ctx: TenantContext, request: Request, key: str | None, ttl: timedelta
    ) -> None:
        self._ctx = ctx
        self._request = request
        self._key = key
        self._ttl = ttl
        self._row_id: Any = None

    @property
    def enabled(self) -> bool:
        return self._key is not None

    def _route(self) -> str:
        route = self._request.scope.get("route")
        return str(getattr(route, "path", self._request.url.path))

    async def _request_hash(self) -> str:
        body = await self._request.body()
        digest = hashlib.sha256()
        for part in (self._request.method.encode(), self._request.url.path.encode(), body):
            digest.update(len(part).to_bytes(8, "big"))
            digest.update(part)
        return digest.hexdigest()

    async def replay(self) -> JSONResponse | None:
        """Claim the key, or return the stored response of an earlier identical request."""
        if self._key is None:
            return None
        session = self._ctx.session
        principal = self._ctx.principal
        request_hash = await self._request_hash()
        scope = {
            "tenant_id": principal.tenant_id,
            "principal_id": principal.user_id,
            "method": self._request.method,
            "route": self._route(),
            "key": self._key,
        }
        claimed = await session.execute(
            insert(IdempotencyKey)
            .values(
                **scope,
                request_hash=request_hash,
                expires_at=func.now() + self._ttl,
            )
            .on_conflict_do_nothing()
            .returning(IdempotencyKey.id)
        )
        self._row_id = claimed.scalar_one_or_none()
        if self._row_id is not None:
            return None

        existing = (await session.execute(select(IdempotencyKey).filter_by(**scope))).scalar_one()
        if existing.request_hash != request_hash or existing.response_status is None:
            raise IdempotencyKeyReusedError()
        headers = dict(existing.response_headers or {})
        headers[REPLAY_HEADER] = "true"
        return JSONResponse(
            existing.response_body, status_code=existing.response_status, headers=headers
        )

    async def respond(
        self, status_code: int, body: BaseModel, headers: dict[str, str] | None = None
    ) -> JSONResponse:
        """Build the response and, if a key was sent, store it with the claimed key."""
        content = jsonable_encoder(body)
        if self._row_id is not None:
            row = await self._ctx.session.get(IdempotencyKey, self._row_id)
            if row is not None:
                row.response_status = status_code
                row.response_body = content
                row.response_headers = headers or {}
        return JSONResponse(content, status_code=status_code, headers=headers)


def idempotency_dependency(
    ctx_dependency: Any,
) -> Any:
    """Build the ``Idempotency`` dependency on top of a ``require_permission(...)`` dependency."""

    async def dependency(
        request: Request,
        resources: ResourcesDep,
        ctx: Annotated[TenantContext, Depends(ctx_dependency)],
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> Idempotency:
        if idempotency_key is not None and not _VALID_KEY.match(idempotency_key):
            raise InvalidIdempotencyKeyError()
        ttl = timedelta(hours=resources.settings.idempotency_ttl_hours)
        return Idempotency(ctx, request, idempotency_key, ttl)

    return dependency


async def purge_expired(session: AsyncSession) -> int:
    """Delete expired keys of **all** tenants via the narrow SECURITY DEFINER function (ADR-0011)."""
    result = await session.execute(text("SELECT app.purge_expired_idempotency_keys()"))
    return int(result.scalar_one())
