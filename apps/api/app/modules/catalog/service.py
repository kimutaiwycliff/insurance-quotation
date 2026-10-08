"""Item catalogue: things a tenant sells, with a default price and tax code (pack data)."""

import uuid
from http import HTTPStatus

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.concurrency import check_version
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.money import minor_unit
from app.modules.catalog.models import Item
from app.modules.catalog.schemas import ItemIn, ItemOut, ItemUpdate
from app.modules.insurers import service as insurers
from app.modules.tenancy import service as tenancy
from app.platform import audit
from app.platform.deps import TenantContext

__all__ = ["Item", "ItemOut", "check_tax_code", "get_item"]


class UnknownTaxCodeError(AppError):
    status = HTTPStatus.UNPROCESSABLE_CONTENT
    code = "unknown_tax_code"
    title = "Unknown tax code"


async def check_tax_code(ctx: TenantContext, code: str) -> None:
    pack, _, _ = await insurers.agency_pack(ctx)
    if code not in {t.code for t in pack.tax_codes}:
        raise UnknownTaxCodeError(f"Use one of: {', '.join(t.code for t in pack.tax_codes)}")


async def list_items(ctx: TenantContext, *, include_inactive: bool) -> list[Item]:
    stmt = select(Item).order_by(Item.name)
    if not include_inactive:
        stmt = stmt.where(Item.active.is_(True))
    return list((await ctx.session.scalars(stmt)).all())


async def get_item(ctx: TenantContext, item_id: uuid.UUID) -> Item:
    item = await ctx.session.get(Item, item_id)
    if item is None:
        raise NotFoundError("Item not found")
    return item


async def _flush(ctx: TenantContext) -> None:
    try:
        await ctx.session.flush()
    except IntegrityError:
        raise ConflictError("An item with this name already exists") from None


async def create_item(ctx: TenantContext, body: ItemIn) -> Item:
    await check_tax_code(ctx, body.tax_code)
    tenant = await tenancy.get_tenant(ctx.session, ctx.tenant_id)
    currency = body.currency or tenant.default_currency
    minor_unit(currency)
    item = Item(
        tenant_id=ctx.tenant_id,
        name=body.name,
        description=body.description,
        unit=body.unit,
        unit_price=body.unit_price,
        currency=currency,
        tax_code=body.tax_code,
        created_by=ctx.principal.user_id,
        updated_by=ctx.principal.user_id,
    )
    ctx.session.add(item)
    await _flush(ctx)
    await ctx.session.refresh(item)
    await audit.record(ctx, "item.created", entity_type="item", entity_id=item.id)
    return item


async def update_item(
    ctx: TenantContext, item_id: uuid.UUID, body: ItemUpdate, if_match: str | None
) -> Item:
    item = await get_item(ctx, item_id)
    check_version(if_match, item.version)
    data = body.model_dump(exclude_unset=True)
    if data.get("tax_code"):
        await check_tax_code(ctx, data["tax_code"])
    for field, value in data.items():
        if value is not None or field in {"description", "unit"}:
            setattr(item, field, value)
    item.updated_by = ctx.principal.user_id
    await _flush(ctx)
    await ctx.session.refresh(item)
    return item


def to_out(item: Item) -> ItemOut:
    return ItemOut.model_validate(item)
