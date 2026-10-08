"""Insurers, products and the premium calculator (ADR-0013).

The calculator turns a product + a risk into a :class:`app.calc.premium.PremiumRequest` using the agency's
jurisdiction pack, and hides commission from roles without ``commission:read:*``.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from http import HTTPStatus
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.calc.pack import Pack
from app.calc.premium import (
    Adjustment,
    Benefit,
    Fee,
    MemberTier,
    PremiumInputError,
    PremiumRequest,
    PremiumResult,
    Rating,
    calculate,
)
from app.core.concurrency import check_version
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.permissions import Perm
from app.jurisdictions.loader import pack_for_country
from app.modules.insurers.models import Insurer, Product
from app.modules.insurers.schemas import (
    CalculateIn,
    CalculationOut,
    CommissionOut,
    CompareIn,
    Comparison,
    InsurerIn,
    InsurerUpdate,
    LineOut,
    ProductIn,
    ProductRef,
    ProductUpdate,
    RiskIn,
)
from app.modules.tenancy import service as tenancy
from app.platform import audit
from app.platform.deps import TenantContext

__all__ = [
    "CalculationOut",
    "Insurer",
    "Product",
    "RiskIn",
    "agency_pack",
    "calculate_product",
    "can_see_commission",
    "get_product",
]


class PremiumCalculationError(AppError):
    status = HTTPStatus.UNPROCESSABLE_CONTENT
    code = "premium_input"
    title = "The premium cannot be calculated from these details"


class UnknownClassError(AppError):
    status = HTTPStatus.UNPROCESSABLE_CONTENT
    code = "unknown_class"
    title = "Unknown class of business"


async def agency_pack(ctx: TenantContext) -> tuple[Pack, str, str]:
    """The agency's jurisdiction pack, its intermediary type and timezone."""
    tenant = await tenancy.get_tenant(ctx.session, ctx.tenant_id)
    return pack_for_country(tenant.country_code), tenant.intermediary_type, tenant.timezone


def can_see_commission(ctx: TenantContext) -> bool:
    perms = ctx.principal.permissions
    return Perm.COMMISSION_READ_ALL in perms or Perm.COMMISSION_READ_OWN in perms


# ---------------------------------------------------------------- insurers


async def list_insurers(ctx: TenantContext, *, include_inactive: bool) -> list[Insurer]:
    stmt = select(Insurer).order_by(Insurer.name)
    if not include_inactive:
        stmt = stmt.where(Insurer.is_active.is_(True))
    return list((await ctx.session.scalars(stmt)).all())


async def get_insurer(ctx: TenantContext, insurer_id: uuid.UUID) -> Insurer:
    insurer = await ctx.session.get(Insurer, insurer_id)
    if insurer is None:
        raise NotFoundError("Insurer not found")
    return insurer


async def _flush_unique(ctx: TenantContext, what: str) -> None:
    try:
        async with ctx.session.begin_nested():
            await ctx.session.flush()
    except IntegrityError:
        raise ConflictError(f"{what} with this name already exists") from None


async def create_insurer(ctx: TenantContext, body: InsurerIn) -> Insurer:
    data = body.model_dump()
    if data["email"]:
        data["email"] = str(data["email"])
    insurer = Insurer(
        tenant_id=ctx.tenant_id,
        created_by=ctx.principal.user_id,
        updated_by=ctx.principal.user_id,
        **data,
    )
    ctx.session.add(insurer)
    await _flush_unique(ctx, "An insurer")
    await ctx.session.refresh(insurer)
    await audit.record(
        ctx,
        "insurer.created",
        entity_type="insurer",
        entity_id=insurer.id,
        changes={"name": insurer.name},
    )
    return insurer


async def update_insurer(
    ctx: TenantContext, insurer_id: uuid.UUID, body: InsurerUpdate, if_match: str | None
) -> Insurer:
    insurer = await get_insurer(ctx, insurer_id)
    check_version(if_match, insurer.version)
    data = body.model_dump(exclude_unset=True)
    if data.get("email"):
        data["email"] = str(data["email"])
    before = {f: getattr(insurer, f) for f in data}
    for field, value in data.items():
        setattr(insurer, field, value)
    insurer.updated_by = ctx.principal.user_id
    await _flush_unique(ctx, "An insurer")
    await ctx.session.refresh(insurer)
    await audit.record(
        ctx,
        "insurer.updated",
        entity_type="insurer",
        entity_id=insurer.id,
        changes=audit.diff(before, {f: getattr(insurer, f) for f in data}),
    )
    return insurer


# ---------------------------------------------------------------- products


async def list_products(
    ctx: TenantContext,
    *,
    insurer_id: uuid.UUID | None,
    class_code: str | None,
    include_inactive: bool,
) -> list[Product]:
    stmt = select(Product).order_by(Product.class_code, Product.name)
    if insurer_id:
        stmt = stmt.where(Product.insurer_id == insurer_id)
    if class_code:
        stmt = stmt.where(Product.class_code == class_code)
    if not include_inactive:
        stmt = stmt.where(Product.is_active.is_(True))
    return list((await ctx.session.scalars(stmt)).all())


async def get_product(ctx: TenantContext, product_id: uuid.UUID) -> Product:
    product = await ctx.session.get(Product, product_id)
    if product is None:
        raise NotFoundError("Product not found")
    return product


async def _check_class(ctx: TenantContext, class_code: str) -> None:
    pack, _, _ = await agency_pack(ctx)
    if pack.insurance_class(class_code) is None:
        raise UnknownClassError(f"{class_code!r} is not a class in the {pack.title} pack")


def _product_values(body: ProductIn | ProductUpdate) -> dict[str, Any]:
    data = body.model_dump(mode="python")
    data["benefits"] = [b.model_dump(mode="json") for b in body.benefits]
    data["member_tiers"] = [t.model_dump(mode="json") for t in body.member_tiers]
    return data


async def create_product(ctx: TenantContext, body: ProductIn) -> Product:
    await get_insurer(ctx, body.insurer_id)
    await _check_class(ctx, body.class_code)
    product = Product(
        tenant_id=ctx.tenant_id,
        created_by=ctx.principal.user_id,
        updated_by=ctx.principal.user_id,
        **_product_values(body),
    )
    ctx.session.add(product)
    await _flush_unique(ctx, "A product")
    await ctx.session.refresh(product)
    await audit.record(
        ctx,
        "product.created",
        entity_type="product",
        entity_id=product.id,
        changes={"name": product.name, "class_code": product.class_code},
    )
    return product


async def update_product(
    ctx: TenantContext, product_id: uuid.UUID, body: ProductUpdate, if_match: str | None
) -> Product:
    """Full replacement of the product terms (a product is edited as one form)."""
    product = await get_product(ctx, product_id)
    check_version(if_match, product.version)
    await _check_class(ctx, body.class_code)
    values = _product_values(body)
    tracked = (
        "rate",
        "flat_premium",
        "min_premium",
        "commission_rate_new",
        "commission_rate_renewal",
        "is_active",
    )
    before = {f: getattr(product, f) for f in tracked}
    for field, value in values.items():
        setattr(product, field, value)
    product.updated_by = ctx.principal.user_id
    await _flush_unique(ctx, "A product")
    await ctx.session.refresh(product)
    await audit.record(
        ctx,
        "product.updated",
        entity_type="product",
        entity_id=product.id,
        changes=audit.diff(before, {f: getattr(product, f) for f in tracked}),
    )
    return product


# ---------------------------------------------------------------- calculator


def _rating(product: Product, risk: RiskIn, rate_override: Decimal | None) -> Rating:
    tiers = {t["label"]: Decimal(t["amount"]) for t in product.member_tiers}
    members = []
    for m in risk.members:
        amount = m.amount if m.amount is not None else tiers.get(m.label)
        if amount is None:
            raise PremiumCalculationError(
                f"No premium for member tier {m.label!r} in {product.name}"
            )
        members.append(MemberTier(label=m.label, count=m.count, amount=amount))
    return Rating(
        basis=product.rating_basis,  # type: ignore[arg-type]
        sum_insured=risk.sum_insured,
        rate=rate_override if rate_override is not None else product.rate,
        flat_amount=product.flat_premium,
        members=members,
        manual_amount=risk.manual_amount,
    )


def _benefits(product: Product, codes: list[str] | None) -> list[Benefit]:
    chosen = []
    for raw in product.benefits:
        selected = (not raw["optional"]) or (
            raw["code"] in codes if codes is not None else raw["selected_by_default"]
        )
        if selected:
            chosen.append(
                Benefit(
                    code=raw["code"],
                    name=raw["name"],
                    basis=raw["basis"],
                    value=Decimal(str(raw["value"])),
                    commissionable=raw.get("commissionable", True),
                )
            )
    if codes is not None:
        unknown = set(codes) - {b["code"] for b in product.benefits}
        if unknown:
            raise PremiumCalculationError(f"{product.name} has no benefit {sorted(unknown)[0]!r}")
    return chosen


def _out(
    result: PremiumResult, product: Product, insurer: Insurer, show_commission: bool, pack: Pack
) -> CalculationOut:
    commission = result.commission
    return CalculationOut(
        product=ProductRef(
            id=product.id,
            name=product.name,
            insurer_id=insurer.id,
            insurer_name=insurer.name,
            class_code=product.class_code,
            excess_text=product.excess_text,
        ),
        currency=result.currency,
        lines=[LineOut(**line.model_dump(exclude={"commissionable"})) for line in result.lines],
        basic_premium=result.basic_premium,
        adjusted_premium=result.adjusted_premium,
        client_total=result.client_total,
        insurer_borne=result.insurer_borne,
        commission=CommissionOut(**commission.model_dump())
        if commission and show_commission
        else None,
        pack={"code": pack.code, "version": pack.version, "signed": pack.signed},
        notes=result.notes,
        needs_input=result.needs_input,
    )


async def calculate_product(
    ctx: TenantContext, product: Product, risk: RiskIn, *, rate_override: Decimal | None = None
) -> tuple[PremiumResult, CalculationOut]:
    pack, intermediary_type, timezone = await agency_pack(ctx)
    insurer = await get_insurer(ctx, product.insurer_id)
    on = risk.on or datetime.now(ZoneInfo(timezone)).date()
    try:
        request = PremiumRequest(
            class_code=product.class_code,
            currency=product.currency,
            on=on,
            document_kind=risk.document_kind,
            rating=_rating(product, risk, rate_override),
            min_premium=product.min_premium,
            benefits=_benefits(product, risk.benefit_codes),
            adjustments=[Adjustment(**a.model_dump()) for a in risk.adjustments],
            fees=[Fee(**f.model_dump()) for f in risk.fees],
            stamp_duty_manual=risk.stamp_duty_manual,
            commission_rate=product.commission_rate_renewal
            if risk.renewal
            else product.commission_rate_new,
            intermediary_type="agent" if intermediary_type == "business" else intermediary_type,  # type: ignore[arg-type]
        )
        result = calculate(pack, request)
    except (PremiumInputError, ValueError) as exc:
        raise PremiumCalculationError(str(exc).splitlines()[0]) from None
    return result, _out(result, product, insurer, can_see_commission(ctx), pack)


async def calculate_one(ctx: TenantContext, body: CalculateIn) -> CalculationOut:
    product = await get_product(ctx, body.product_id)
    _, out = await calculate_product(ctx, product, body, rate_override=body.rate)
    return out


async def compare(ctx: TenantContext, body: CompareIn) -> Comparison:
    """Price the same risk with several products (multi-insurer comparison), cheapest first."""
    results, errors = [], []
    for product_id in dict.fromkeys(body.product_ids):
        product = await get_product(ctx, product_id)
        try:
            _, out = await calculate_product(ctx, product, body)
        except PremiumCalculationError as exc:
            errors.append(
                {
                    "product_id": str(product_id),
                    "product": product.name,
                    "error": exc.detail or exc.title,
                }
            )
            continue
        results.append(out)
    results.sort(key=lambda r: (bool(r.needs_input), r.client_total))
    return Comparison(results=results, errors=errors)
