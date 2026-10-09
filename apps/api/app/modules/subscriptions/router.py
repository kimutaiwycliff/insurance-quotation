"""Plan & billing endpoints, and the callback for the platform's own M-Pesa shortcode."""

import secrets
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.db import set_tenant_context
from app.core.errors import NotFoundError
from app.core.permissions import Perm
from app.modules.billing import service as billing
from app.modules.clients import service as clients
from app.modules.subscriptions import service
from app.modules.subscriptions.models import SubscriptionPayment
from app.modules.subscriptions.plans import FOUNDING_MEMBERS, PLANS
from app.modules.subscriptions.schemas import (
    Checkout,
    PlanOut,
    PlanPrice,
    SubscriptionOut,
    SubscriptionPaymentOut,
    Usage,
)
from app.modules.tenancy import service as tenancy
from app.platform.deps import ResourcesDep, TenantContext, require_permission

router = APIRouter(prefix="/subscription", tags=["subscription"])
# Reading and paying stay possible when the subscription has lapsed (that is how it is renewed).
Read = Annotated[TenantContext, Depends(require_permission(Perm.ORG_READ, allow_read_only=True))]
Pay = Annotated[TenantContext, Depends(require_permission(Perm.ORG_UPDATE, allow_read_only=True))]


def _payment_out(p: SubscriptionPayment) -> SubscriptionPaymentOut:
    return SubscriptionPaymentOut(
        id=p.id,
        plan=p.plan,
        billing_cycle=p.billing_cycle,
        extra_seats=p.extra_seats,
        list_price=p.list_price.quantize(Decimal("0.01")),
        discount_percent=p.discount_percent,
        amount=p.amount.quantize(Decimal(1)),
        status=p.status,
        receipt=p.receipt,
        result_desc=p.result_desc,
        period_start=p.period_start,
        period_end=p.period_end,
        created_at=p.created_at,
        completed_at=p.completed_at,
    )


@router.get("", operation_id="subscription_get")
async def get_subscription(ctx: Read) -> SubscriptionOut:
    sub, granted = await service.current(ctx)
    today = datetime.now(UTC).date()
    members = [m for m in await tenancy.list_members(ctx.session) if m.status == "active"]
    taken = int(await ctx.session.scalar(text("SELECT app.founding_members_count()")) or 0)
    return SubscriptionOut(
        plan=granted.plan,
        plan_name=PLANS[granted.plan].name,
        paid_plan=sub.plan,
        status=granted.status,
        billing_cycle=sub.billing_cycle,
        trial_ends_at=sub.trial_ends_at,
        period_end=sub.current_period_end,
        seats=granted.seats,
        founding_member=sub.founding_member,
        discount_percent=sub.discount_percent,
        discount_until=sub.discount_until,
        features=sorted(granted.features),
        limits=granted.limits,
        usage=Usage(
            clients=await clients.count_clients(ctx),
            documents_this_month=await billing.documents_issued_since(
                ctx.session, today.replace(day=1)
            ),
            seats_used=len(members),
        ),
        founding_places_left=max(FOUNDING_MEMBERS - taken, 0),
    )


@router.get("/plans", operation_id="subscription_plans")
async def plans(ctx: Read) -> list[PlanOut]:
    """Plans with prices for this agency now (the founding discount applies to the first 100 to pay)."""
    sub, _ = await service.current(ctx)
    out = []
    for plan in PLANS.values():
        prices = []
        if plan.code != "free":
            for cycle in ("monthly", "yearly"):
                q = await service.quote_price(ctx.session, sub, plan.code, cycle, 0)
                prices.append(
                    PlanPrice(
                        cycle=cycle,
                        list_price=q.list_price,
                        price=q.amount,
                        discount_percent=q.discount_percent,
                    )
                )
        out.append(
            PlanOut(
                code=plan.code,
                name=plan.name,
                tagline=plan.tagline,
                included_seats=plan.included_seats,
                extra_seat_monthly=plan.extra_seat_monthly,
                features=sorted(str(f) for f in plan.features),
                limits={str(k): v for k, v in plan.limits.items()},
                prices=prices,
            )
        )
    return out


@router.post("/checkout", operation_id="subscription_checkout", status_code=201)
async def checkout(ctx: Pay, body: Checkout, resources: ResourcesDep) -> SubscriptionPaymentOut:
    """Pay for a plan by M-Pesa: a prompt goes to the phone; poll the payment until it is paid."""
    service.ensure_not_pending(await service.list_payments(ctx))
    payment = await service.checkout(
        ctx,
        plan_code=body.plan,
        cycle=body.cycle,
        extra_seats=body.extra_seats,
        phone=body.phone,
        settings=resources.settings,
        http=resources.http,
    )
    return _payment_out(payment)


@router.get("/payments", operation_id="subscription_payments_list")
async def payments(ctx: Read) -> list[SubscriptionPaymentOut]:
    return [_payment_out(p) for p in await service.list_payments(ctx)]


@router.get("/payments/{payment_id}", operation_id="subscription_payment_get")
async def payment(
    ctx: Read, payment_id: uuid.UUID, resources: ResourcesDep
) -> SubscriptionPaymentOut:
    return _payment_out(
        await service.payment_status(ctx, payment_id, resources.settings, resources.http)
    )


webhook_router = APIRouter(prefix="/webhooks/mpesa-platform", include_in_schema=False)
_ACCEPTED = {"ResultCode": 0, "ResultDesc": "Accepted"}


@webhook_router.post("/{secret}/stk")
async def platform_stk_callback(
    secret: Annotated[str, Path(max_length=200)],
    payload: dict[str, Any],
    request: Request,
    resources: ResourcesDep,
) -> JSONResponse:
    """Safaricom's answer for a subscription payment prompt: confirmed with STK Query before it counts."""
    settings = resources.settings
    if not secrets.compare_digest(
        secret, settings.platform_mpesa_callback_secret.get_secret_value()
    ):
        raise NotFoundError("Unknown callback")
    allowed = {ip.strip() for ip in settings.mpesa_callback_allowed_ips.split(",") if ip.strip()}
    if allowed and (request.client.host if request.client else "") not in allowed:
        raise NotFoundError("Unknown callback")
    checkout_id, _, receipt = service.receipt_from_callback(payload)
    async with resources.session_factory() as session, session.begin():
        resolved = await service.resolve_callback(session, checkout_id) if checkout_id else None
        if resolved is not None:
            tenant_id, payment_id = resolved
            await set_tenant_context(session, tenant_id)
            await service.check_payment(
                session, settings, resources.http, payment_id, receipt=receipt
            )
    return JSONResponse(_ACCEPTED)
