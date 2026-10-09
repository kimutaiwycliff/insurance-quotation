"""Subscriptions (Plan A1.3 R2.5, docs/PRICING.md): what a tenant may use, and paying us for it by M-Pesa.

- **Effective plan:** a running trial grants the trial plan (Agent) for 30 days; a paid plan holds until
  ``current_period_end``, then a 7-day grace period (past due, full access), then **read-only** (nothing is
  deleted; paying again restores it). Free never becomes read-only: it has limits instead.
- **Enforcement:** features through ``require_feature`` on routes; limits (clients, documents a month,
  seats) by the module that owns the data, which passes its own count to ``check_limit``.
- **Paying:** an STK Push to the payer's phone from the **platform's** own shortcode; a payment counts only
  after STK Query confirms it, then the period is extended. The first 100 paying tenants get the founding
  discount (50% for 12 months).
"""

import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from http import HTTPStatus
from typing import Any

import httpx
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.phone import InvalidPhoneError, to_e164
from app.integrations.mpesa import Credentials, DarajaError, client_for, simulated_receipt
from app.modules.subscriptions.models import Subscription, SubscriptionPayment
from app.modules.subscriptions.plans import (
    FOUNDING_DISCOUNT_PERCENT,
    FOUNDING_MEMBERS,
    FOUNDING_MONTHS,
    GRACE_DAYS,
    PLANS,
    TRIAL_DAYS,
    TRIAL_PLAN,
    Feature,
    Limit,
    Plan,
    price,
)
from app.platform.deps import TenantContext

__all__ = [
    "Entitlements",
    "Feature",
    "Limit",
    "check_feature",
    "check_limit",
    "entitlements",
    "start_trial",
]

PENDING, PAID, CANCELLED, FAILED, EXPIRED = "pending", "paid", "cancelled", "failed", "expired"
RECHECK_AFTER = timedelta(seconds=8)
PROMPT_TTL = timedelta(minutes=5)


class LimitReachedError(AppError):
    status = HTTPStatus.PAYMENT_REQUIRED
    code = "plan_limit"
    title = "Your plan's limit is reached"


class FeatureNotInPlanError(AppError):
    status = HTTPStatus.PAYMENT_REQUIRED
    code = "plan_feature"
    title = "Your plan does not include this"


class BillingError(AppError):
    status = HTTPStatus.UNPROCESSABLE_CONTENT
    code = "subscription_payment"
    title = "The payment could not be started"


@dataclass(frozen=True, slots=True)
class Entitlements:
    plan: str  # the effective plan (the trial plan during a trial)
    paid_plan: str
    status: str  # trialing | active | past_due | read_only | free
    features: frozenset[str]
    limits: dict[str, int] = field(default_factory=dict)
    seats: int = 1
    trial_ends_at: datetime | None = None
    period_end: date | None = None
    billing_cycle: str = "monthly"
    founding_member: bool = False

    @property
    def read_only(self) -> bool:
        return self.status == "read_only"


def _effective(sub: Subscription, now: datetime) -> Entitlements:
    today = now.date()
    paid = PLANS[sub.plan]
    if sub.plan != "free" and sub.current_period_end is not None:
        if today <= sub.current_period_end:
            status = "active"
        elif today <= sub.current_period_end + timedelta(days=GRACE_DAYS):
            status = "past_due"
        else:
            status = "read_only"
        plan = paid
    elif sub.trial_ends_at is not None and now < sub.trial_ends_at:
        status, plan = "trialing", PLANS[TRIAL_PLAN]
    else:
        status, plan = "free", PLANS["free"]
    return Entitlements(
        plan=plan.code,
        paid_plan=sub.plan,
        status=status,
        features=frozenset(str(f) for f in plan.features),
        limits={str(k): v for k, v in plan.limits.items()},
        seats=plan.included_seats + (sub.extra_seats if plan.code == sub.plan else 0),
        trial_ends_at=sub.trial_ends_at,
        period_end=sub.current_period_end,
        billing_cycle=sub.billing_cycle,
        founding_member=sub.founding_member,
    )


async def start_trial(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """A new agency gets the trial (idempotent: an existing subscription is left alone)."""
    await session.execute(
        insert(Subscription)
        .values(
            tenant_id=tenant_id,
            plan="free",
            trial_ends_at=datetime.now(UTC) + timedelta(days=TRIAL_DAYS),
        )
        .on_conflict_do_nothing()
    )


async def _subscription(
    session: AsyncSession, tenant_id: uuid.UUID, *, lock: bool = False
) -> Subscription:
    stmt = select(Subscription)
    sub = (await session.scalars(stmt.with_for_update() if lock else stmt)).first()
    if sub is None:
        await start_trial(session, tenant_id)
        sub = (await session.scalars(stmt.with_for_update() if lock else stmt)).one()
    return sub


async def entitlements(session: AsyncSession, tenant_id: uuid.UUID) -> Entitlements:
    return _effective(await _subscription(session, tenant_id), datetime.now(UTC))


def check_feature(ctx: TenantContext, feature: Feature) -> None:
    features = ctx.principal.features
    if "*" not in features and str(feature) not in features:
        raise FeatureNotInPlanError(f"Upgrade your plan to use {feature.value.replace('_', ' ')}")


_LIMIT_TEXT = {
    Limit.CLIENTS: "clients",
    Limit.DOCUMENTS_PER_MONTH: "invoices and quotes a month",
    Limit.SEATS: "team members",
}


async def check_limit(
    session: AsyncSession, tenant_id: uuid.UUID, limit: Limit, current: int
) -> None:
    """Refuse adding one more of ``limit`` when ``current`` already reaches the plan's allowance."""
    granted = await entitlements(session, tenant_id)
    allowed = granted.seats if limit is Limit.SEATS else granted.limits.get(str(limit))
    if allowed is not None and current >= allowed:
        name = PLANS[granted.plan].name
        raise LimitReachedError(
            f"The {name} plan includes {allowed} {_LIMIT_TEXT[limit]}. Upgrade to add more."
        )


# ---------------------------------------------------------------- prices


@dataclass(frozen=True, slots=True)
class PriceQuote:
    plan: Plan
    cycle: str
    extra_seats: int
    list_price: Decimal
    discount_percent: int
    amount: Decimal  # whole shillings
    founding: bool


async def _founding_open(session: AsyncSession) -> bool:
    taken = await session.scalar(text("SELECT app.founding_members_count()"))
    return int(taken or 0) < FOUNDING_MEMBERS


async def quote_price(
    session: AsyncSession, sub: Subscription, plan_code: str, cycle: str, extra_seats: int
) -> PriceQuote:
    plan = PLANS.get(plan_code)
    if plan is None or plan.code == "free":
        raise BillingError("Choose a paid plan")
    if extra_seats and plan.extra_seat_monthly is None:
        raise BillingError(f"The {plan.name} plan has a fixed number of users")
    list_price = price(plan, cycle, extra_seats)
    today = datetime.now(UTC).date()
    founding = sub.founding_member or await _founding_open(session)
    discount = 0
    if sub.founding_member and sub.discount_until and today <= sub.discount_until:
        discount = sub.discount_percent
    elif not sub.founding_member and founding:
        discount = FOUNDING_DISCOUNT_PERCENT
    amount = Decimal(math.ceil(list_price * (100 - discount) / 100))
    return PriceQuote(
        plan, cycle, extra_seats, list_price, discount, amount, founding and discount > 0
    )


# ---------------------------------------------------------------- paying (platform M-Pesa)


def _credentials(settings: Settings) -> Credentials:
    till = settings.platform_mpesa_shortcode_type == "till"
    return Credentials(
        environment=settings.platform_mpesa_environment,  # type: ignore[arg-type]
        consumer_key=settings.platform_mpesa_consumer_key.get_secret_value(),
        consumer_secret=settings.platform_mpesa_consumer_secret.get_secret_value(),
        business_shortcode=settings.platform_mpesa_shortcode,
        passkey=settings.platform_mpesa_passkey.get_secret_value(),
        party_b=settings.platform_mpesa_till_number if till else settings.platform_mpesa_shortcode,
        transaction_type="CustomerBuyGoodsOnline" if till else "CustomerPayBillOnline",
    )


def callback_url(settings: Settings) -> str:
    secret = settings.platform_mpesa_callback_secret.get_secret_value()
    return f"{settings.public_api_base_url.rstrip('/')}/api/v1/webhooks/mpesa-platform/{secret}/stk"


async def checkout(
    ctx: TenantContext,
    *,
    plan_code: str,
    cycle: str,
    extra_seats: int,
    phone: str,
    settings: Settings,
    http: httpx.AsyncClient,
) -> SubscriptionPayment:
    sub = await _subscription(ctx.session, ctx.tenant_id, lock=True)
    quote = await quote_price(ctx.session, sub, plan_code, cycle, extra_seats)
    try:
        msisdn = to_e164(phone)
    except InvalidPhoneError:
        raise BillingError("Enter the M-Pesa number like 0712 345 678") from None
    if not msisdn.startswith("+254"):
        raise BillingError("M-Pesa payments come from Kenyan numbers only")
    payment = SubscriptionPayment(
        tenant_id=ctx.tenant_id,
        plan=quote.plan.code,
        billing_cycle=cycle,
        extra_seats=extra_seats,
        list_price=quote.list_price,
        discount_percent=quote.discount_percent,
        amount=quote.amount,
        phone=msisdn,
        requested_by=ctx.principal.user_id,
    )
    ctx.session.add(payment)
    await ctx.session.flush()
    try:
        accepted = await client_for(_credentials(settings), http).stk_push(
            phone=msisdn.lstrip("+"),
            amount=int(quote.amount),
            account_reference=f"SUB{str(ctx.tenant_id)[:8]}".upper(),
            description=f"{quote.plan.name} plan",
            callback_url=callback_url(settings),
        )
    except DarajaError as exc:
        payment.status, payment.result_desc, payment.completed_at = (
            FAILED,
            exc.detail,
            datetime.now(UTC),
        )
        await ctx.session.flush()
        raise BillingError(exc.detail) from None
    payment.checkout_request_id = accepted.checkout_request_id
    payment.result_desc = accepted.customer_message
    await ctx.session.flush()
    await ctx.session.refresh(payment)
    return payment


def _next_period(sub: Subscription, cycle: str, today: date) -> tuple[date, date]:
    start = (
        sub.current_period_end + timedelta(days=1)
        if sub.current_period_end and sub.current_period_end >= today
        else today
    )
    months = 12 if cycle == "yearly" else 1
    year, month = divmod(start.month - 1 + months, 12)
    try:
        end = start.replace(year=start.year + year, month=month + 1) - timedelta(days=1)
    except ValueError:  # e.g. 31 Jan + 1 month
        end = (
            start.replace(day=1, year=start.year + year, month=month + 1) + timedelta(days=27)
        ).replace(day=28)
    return start, end


async def _activate(session: AsyncSession, payment: SubscriptionPayment, receipt: str) -> None:
    sub = await _subscription(session, payment.tenant_id, lock=True)
    today = datetime.now(UTC).date()
    if sub.plan != payment.plan:
        sub.current_period_end = None  # a plan change starts a fresh period today
    start, end = _next_period(sub, payment.billing_cycle, today)
    sub.plan, sub.billing_cycle, sub.extra_seats = (
        payment.plan,
        payment.billing_cycle,
        payment.extra_seats,
    )
    sub.current_period_end, sub.trial_ends_at = end, None
    if payment.discount_percent and not sub.founding_member:
        sub.founding_member, sub.discount_percent = True, payment.discount_percent
        sub.discount_until = today + timedelta(days=round(FOUNDING_MONTHS * 30.44))
    payment.status, payment.receipt, payment.completed_at = PAID, receipt, datetime.now(UTC)
    payment.period_start, payment.period_end = start, end
    await session.flush()


async def check_payment(
    session: AsyncSession,
    settings: Settings,
    http: httpx.AsyncClient,
    payment_id: uuid.UUID,
    *,
    receipt: str | None = None,
) -> SubscriptionPayment:
    """Confirm a pending payment with STK Query (polls, the callback). Idempotent."""
    payment = await session.get(
        SubscriptionPayment, payment_id, with_for_update=True, populate_existing=True
    )
    if payment is None:
        raise NotFoundError("Payment not found")
    if payment.status != PENDING or payment.checkout_request_id is None:
        return payment
    try:
        status = await client_for(_credentials(settings), http).stk_query(
            payment.checkout_request_id
        )
    except DarajaError:
        status = None
    if status is not None and status.result_code == 0:
        code = receipt or (
            simulated_receipt(payment.checkout_request_id)
            if settings.platform_mpesa_environment == "simulator"
            else f"STK{payment.checkout_request_id[-9:]}"
        )
        await _activate(session, payment, code)
    elif status is not None and status.result_code is not None:
        payment.status = {1032: CANCELLED, 1037: EXPIRED}.get(status.result_code, FAILED)
        payment.result_desc, payment.completed_at = status.result_desc, datetime.now(UTC)
    elif datetime.now(UTC) - payment.created_at > PROMPT_TTL:
        payment.status, payment.result_desc, payment.completed_at = (
            EXPIRED,
            "No answer from the phone",
            datetime.now(UTC),
        )
    await session.flush()
    return payment


async def payment_status(
    ctx: TenantContext, payment_id: uuid.UUID, settings: Settings, http: httpx.AsyncClient
) -> SubscriptionPayment:
    payment = await ctx.session.get(SubscriptionPayment, payment_id)
    if payment is None:
        raise NotFoundError("Payment not found")
    if payment.status == PENDING and datetime.now(UTC) - payment.created_at > RECHECK_AFTER:
        payment = await check_payment(ctx.session, settings, http, payment_id)
    return payment


async def resolve_callback(
    session: AsyncSession, checkout_request_id: str
) -> tuple[uuid.UUID, uuid.UUID] | None:
    row = (
        await session.execute(
            text("SELECT tenant_id, payment_id FROM app.resolve_subscription_payment(:c)"),
            {"c": checkout_request_id},
        )
    ).first()
    return (row.tenant_id, row.payment_id) if row else None


def receipt_from_callback(payload: dict[str, Any]) -> tuple[str, int, str | None]:
    callback = payload.get("Body", {}).get("stkCallback", {})
    items = {
        str(i.get("Name")): i.get("Value")
        for i in (callback.get("CallbackMetadata") or {}).get("Item", [])
        if isinstance(i, dict)
    }
    receipt = items.get("MpesaReceiptNumber")
    return (
        str(callback.get("CheckoutRequestID") or ""),
        int(callback.get("ResultCode", -1)),
        str(receipt) if receipt else None,
    )


async def list_payments(ctx: TenantContext) -> list[SubscriptionPayment]:
    stmt = select(SubscriptionPayment).order_by(SubscriptionPayment.created_at.desc()).limit(50)
    return list((await ctx.session.scalars(stmt)).all())


async def current(ctx: TenantContext) -> tuple[Subscription, Entitlements]:
    sub = await _subscription(ctx.session, ctx.tenant_id)
    return sub, _effective(sub, datetime.now(UTC))


def ensure_not_pending(payments: list[SubscriptionPayment]) -> None:
    if any(
        p.status == PENDING and datetime.now(UTC) - p.created_at < timedelta(seconds=60)
        for p in payments
    ):
        raise ConflictError(
            "A payment prompt is already waiting on a phone; answer it or wait a minute"
        )
