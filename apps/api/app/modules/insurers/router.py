"""Insurers, products, the agency's jurisdiction pack, and the premium calculator."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response

from app.core.concurrency import etag
from app.core.permissions import Perm
from app.modules.insurers import service
from app.modules.insurers.models import Product
from app.modules.insurers.schemas import (
    CalculateIn,
    CalculationOut,
    CompareIn,
    Comparison,
    InsuranceClassOut,
    InsurerIn,
    InsurerOut,
    InsurerUpdate,
    PackOut,
    ProductIn,
    ProductOut,
    ProductUpdate,
)
from app.platform.deps import TenantContext, require_permission
from app.platform.idempotency import Idempotency, idempotency_dependency

router = APIRouter(tags=["insurers"])
_manage = require_permission(Perm.INSURER_MANAGE)
Read = Annotated[TenantContext, Depends(require_permission(Perm.INSURER_READ))]
Manage = Annotated[TenantContext, Depends(_manage)]
IfMatch = Annotated[str | None, Header()]


def _product_out(ctx: TenantContext, product: Product) -> ProductOut:
    out = ProductOut.model_validate(product)
    if not service.can_see_commission(ctx):
        out = out.model_copy(update={"commission_rate_new": None, "commission_rate_renewal": None})
    return out


@router.get("/jurisdiction-pack", operation_id="jurisdiction_pack_get")
async def jurisdiction_pack(ctx: Read) -> PackOut:
    """The statutory rules this agency's premiums use, and whether they are signed off (D4)."""
    pack, _, _ = await service.agency_pack(ctx)
    return PackOut(
        code=pack.code,
        version=pack.version,
        title=pack.title,
        signed=pack.signed,
        sign_off_note=pack.sign_off.note,
        classes=[InsuranceClassOut(**c.model_dump()) for c in pack.classes],
    )


@router.get("/insurers", operation_id="insurers_list")
async def list_insurers(ctx: Read, include_inactive: bool = False) -> list[InsurerOut]:
    return [
        InsurerOut.model_validate(i)
        for i in await service.list_insurers(ctx, include_inactive=include_inactive)
    ]


@router.post(
    "/insurers", operation_id="insurers_create", status_code=201, response_model=InsurerOut
)
async def create_insurer(
    ctx: Manage,
    body: InsurerIn,
    idem: Annotated[Idempotency, Depends(idempotency_dependency(_manage))],
) -> Response:
    if (replay := await idem.replay()) is not None:
        return replay
    insurer = await service.create_insurer(ctx, body)
    return await idem.respond(
        201, InsurerOut.model_validate(insurer), {"ETag": etag(insurer.version)}
    )


@router.get("/insurers/{insurer_id}", operation_id="insurers_get")
async def get_insurer(ctx: Read, insurer_id: uuid.UUID, response: Response) -> InsurerOut:
    insurer = await service.get_insurer(ctx, insurer_id)
    response.headers["ETag"] = etag(insurer.version)
    return InsurerOut.model_validate(insurer)


@router.patch("/insurers/{insurer_id}", operation_id="insurers_update")
async def update_insurer(
    ctx: Manage,
    insurer_id: uuid.UUID,
    body: InsurerUpdate,
    response: Response,
    if_match: IfMatch = None,
) -> InsurerOut:
    insurer = await service.update_insurer(ctx, insurer_id, body, if_match)
    response.headers["ETag"] = etag(insurer.version)
    return InsurerOut.model_validate(insurer)


@router.get("/products", operation_id="products_list")
async def list_products(
    ctx: Read,
    insurer_id: uuid.UUID | None = None,
    class_code: Annotated[str | None, Query(max_length=40)] = None,
    include_inactive: bool = False,
) -> list[ProductOut]:
    rows = await service.list_products(
        ctx, insurer_id=insurer_id, class_code=class_code, include_inactive=include_inactive
    )
    return [_product_out(ctx, p) for p in rows]


@router.post(
    "/products", operation_id="products_create", status_code=201, response_model=ProductOut
)
async def create_product(
    ctx: Manage,
    body: ProductIn,
    idem: Annotated[Idempotency, Depends(idempotency_dependency(_manage))],
) -> Response:
    if (replay := await idem.replay()) is not None:
        return replay
    product = await service.create_product(ctx, body)
    return await idem.respond(201, _product_out(ctx, product), {"ETag": etag(product.version)})


@router.get("/products/{product_id}", operation_id="products_get")
async def get_product(ctx: Read, product_id: uuid.UUID, response: Response) -> ProductOut:
    product = await service.get_product(ctx, product_id)
    response.headers["ETag"] = etag(product.version)
    return _product_out(ctx, product)


@router.put("/products/{product_id}", operation_id="products_update")
async def update_product(
    ctx: Manage,
    product_id: uuid.UUID,
    body: ProductUpdate,
    response: Response,
    if_match: IfMatch = None,
) -> ProductOut:
    """Replace the product's terms (If-Match). Quotes already issued keep their own snapshot (R1.3)."""
    product = await service.update_product(ctx, product_id, body, if_match)
    response.headers["ETag"] = etag(product.version)
    return _product_out(ctx, product)


@router.post("/premium/calculate", operation_id="premium_calculate")
async def calculate(ctx: Read, body: CalculateIn) -> CalculationOut:
    """Price one product for a risk: premium, benefits, levies, stamp duty, fees and (if allowed) commission."""
    return await service.calculate_one(ctx, body)


@router.post("/premium/compare", operation_id="premium_compare")
async def compare(ctx: Read, body: CompareIn) -> Comparison:
    """Price the same risk with up to 8 products from different insurers, cheapest first."""
    return await service.compare(ctx, body)
