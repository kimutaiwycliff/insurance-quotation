"""Numbering scheme endpoints (settings → numbering)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response

from app.core.concurrency import etag
from app.core.permissions import Perm
from app.modules.numbering import service
from app.modules.numbering.schemas import (
    NumberingPreviewOut,
    NumberingPreviewRequest,
    SchemeCreate,
    SchemeOut,
    SchemeUpdate,
)
from app.platform.deps import TenantContext, require_permission
from app.platform.idempotency import Idempotency, idempotency_dependency

router = APIRouter(prefix="/numbering-schemes", tags=["numbering"])

_read = require_permission(Perm.NUMBERING_READ)
_manage = require_permission(Perm.NUMBERING_MANAGE)
ReadCtx = Annotated[TenantContext, Depends(_read)]
ManageCtx = Annotated[TenantContext, Depends(_manage)]
IfMatch = Annotated[str | None, Header()]


@router.get("", operation_id="numbering_schemes_list")
async def list_schemes(ctx: ReadCtx) -> list[SchemeOut]:
    return [SchemeOut.model_validate(s) for s in await service.list_schemes(ctx.session)]


@router.post("", operation_id="numbering_schemes_create", status_code=201, response_model=SchemeOut)
async def create_scheme(
    ctx: ManageCtx,
    body: SchemeCreate,
    idem: Annotated[Idempotency, Depends(idempotency_dependency(_manage))],
) -> Response:
    if (replay := await idem.replay()) is not None:
        return replay
    scheme = await service.create_scheme(ctx, body)
    return await idem.respond(201, SchemeOut.model_validate(scheme), {"ETag": etag(scheme.version)})


@router.patch("/{scheme_id}", operation_id="numbering_schemes_update")
async def update_scheme(
    ctx: ManageCtx,
    scheme_id: uuid.UUID,
    body: SchemeUpdate,
    response: Response,
    if_match: IfMatch = None,
) -> SchemeOut:
    scheme = await service.update_scheme(ctx, scheme_id, body, if_match)
    response.headers["ETag"] = etag(scheme.version)
    return SchemeOut.model_validate(scheme)


@router.post("/preview", operation_id="numbering_schemes_preview")
async def preview(ctx: ReadCtx, body: NumberingPreviewRequest) -> NumberingPreviewOut:
    return NumberingPreviewOut(
        examples=service.preview(
            body.pattern, body.on or datetime.now(UTC).date(), body.branch_code
        )
    )
