"""Item catalogue endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response

from app.core.concurrency import etag
from app.core.permissions import Perm
from app.modules.catalog import service
from app.modules.catalog.schemas import ItemIn, ItemOut, ItemUpdate
from app.platform.deps import TenantContext, require_permission

router = APIRouter(prefix="/items", tags=["catalog"])
Read = Annotated[
    TenantContext,
    Depends(require_permission((Perm.INVOICE_WRITE, Perm.CATALOG_MANAGE, Perm.CLIENT_READ_ALL))),
]
Manage = Annotated[TenantContext, Depends(require_permission(Perm.CATALOG_MANAGE))]


@router.get("", operation_id="items_list")
async def list_items(ctx: Read, include_inactive: bool = False) -> list[ItemOut]:
    return [
        service.to_out(i) for i in await service.list_items(ctx, include_inactive=include_inactive)
    ]


@router.post("", operation_id="items_create", status_code=201)
async def create_item(ctx: Manage, body: ItemIn, response: Response) -> ItemOut:
    item = await service.create_item(ctx, body)
    response.headers["ETag"] = etag(item.version)
    return service.to_out(item)


@router.patch("/{item_id}", operation_id="items_update")
async def update_item(
    ctx: Manage,
    item_id: uuid.UUID,
    body: ItemUpdate,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
) -> ItemOut:
    item = await service.update_item(ctx, item_id, body, if_match)
    response.headers["ETag"] = etag(item.version)
    return service.to_out(item)
