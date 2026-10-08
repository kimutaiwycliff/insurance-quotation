"""Book import endpoints: preview (nothing saved), then import."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.core.permissions import Perm
from app.modules.imports import service
from app.modules.imports.schemas import ImportPreview, ImportRequest, ImportResult
from app.platform.deps import ResourcesDep, TenantContext, require_permission
from app.platform.idempotency import Idempotency, idempotency_dependency

router = APIRouter(prefix="/imports", tags=["imports"])
_write = require_permission(Perm.CLIENT_WRITE)
Write = Annotated[TenantContext, Depends(_write)]


@router.post("/policies/preview", operation_id="imports_policies_preview")
async def preview(ctx: Write, body: ImportRequest, resources: ResourcesDep) -> ImportPreview:
    """Read the file, detect the columns and check every row. Nothing is saved."""
    return await service.preview(ctx, body, resources.settings)


@router.post(
    "/policies", operation_id="imports_policies_run", status_code=201, response_model=ImportResult
)
async def run(
    ctx: Write,
    body: ImportRequest,
    resources: ResourcesDep,
    idem: Annotated[Idempotency, Depends(idempotency_dependency(_write))],
) -> Response:
    """Import the clients and policies (all in one transaction)."""
    if (replay := await idem.replay()) is not None:
        return replay
    return await idem.respond(201, await service.run_import(ctx, body, resources.settings))
