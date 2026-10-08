"""Policy book and renewals (Plan A1.1 R1.4).

A policy is cover the agent placed with an insurer: from an accepted quote, or entered by hand (an existing
client's cover). By default the client pays the insurer directly (``insurer_direct``). If the insurer authorises
the agent to collect, the agent must remit **immediately** (Regs r.42): recording such a payment opens a
same-day "remit" task. The platform only records payments; it never holds or moves money (CLAUDE.md rule 5).

"No premium, no cover" (Insurance Act s.156): a policy activates only once the insurer confirms cover **and**
either the premium is paid in full or one of the jurisdiction pack's exceptions (Regs r.43) applies.

Renewals: active policies near expiry appear on the renewal board (due → contacted → quoted → renewed | lost).
A daily job reminds the owner at the agency's offsets (default 30/14/7 days) and, if the agency enables it,
emails the client. Each (policy, offset) is reminded once.
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from http import HTTPStatus
from typing import Any
from urllib.parse import quote as urlquote
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.concurrency import check_version
from app.core.config import Settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.money import Money
from app.core.permissions import Perm
from app.modules.clients import service as clients
from app.modules.insurers import service as insurers
from app.modules.messaging import service as messaging
from app.modules.notifications import service as notifications
from app.modules.policies.models import Policy, PolicyPayment, RenewalReminder

__all__ = ["Policy"]
from app.modules.policies.schemas import (
    Activate,
    Cancel,
    FromQuote,
    PaymentIn,
    PaymentOut,
    PolicyCreate,
    PolicyOut,
    PolicySummary,
    PolicyUpdate,
    PremiumExceptionOut,
    Remind,
    Remitted,
    RenewalBoard,
    RenewalColumn,
    RenewalItem,
    RenewalQuote,
    RenewalUpdate,
    VoidPayment,
)
from app.modules.quotes import service as quotes
from app.modules.tasks import service as tasks
from app.modules.tenancy import service as tenancy
from app.platform import audit, events
from app.platform.deps import TenantContext, own_scope

REMIND_RENEWAL = "policies.remind_renewal"
PENDING, ACTIVE, EXPIRED, CANCELLED = "pending", "active", "expired", "cancelled"
STAGES = ("due", "contacted", "quoted", "renewed", "lost")
CLOSED_STAGES = {"renewed", "lost"}


class PolicyStateError(ConflictError):
    code = "policy_state"
    title = "The policy cannot do that in its current state"


class PremiumNotPaidError(AppError):
    status = HTTPStatus.UNPROCESSABLE_CONTENT
    code = "premium_not_paid"
    title = "No premium, no cover: record the payment or choose an exception that applies"


class ReasonRequiredError(AppError):
    status = HTTPStatus.UNPROCESSABLE_CONTENT
    code = "reason_required"
    title = "Say why the renewal was lost"


class PolicyExistsError(ConflictError):
    code = "policy_exists"
    title = "A policy already exists for this quote"


# ---------------------------------------------------------------- helpers


async def _today(session: AsyncSession, tenant_id: uuid.UUID) -> date:
    tenant = await tenancy.get_tenant(session, tenant_id)
    return datetime.now(ZoneInfo(tenant.timezone)).date()


def effective_status(policy: Policy, today: date) -> str:
    return EXPIRED if policy.status == ACTIVE and policy.end_date < today else policy.status


def _scoped[*Ts](stmt: Select[*Ts], ctx: TenantContext) -> Select[*Ts]:
    owner = own_scope(ctx.principal, Perm.CLIENT_READ_ALL)
    return stmt if owner is None else stmt.where(Policy.owner_user_id == owner)


async def get_policy(ctx: TenantContext, policy_id: uuid.UUID, *, lock: bool = False) -> Policy:
    stmt = _scoped(select(Policy).where(Policy.id == policy_id), ctx)
    policy = (await ctx.session.scalars(stmt.with_for_update() if lock else stmt)).first()
    if policy is None:
        raise NotFoundError("Policy not found")
    return policy


def _year_end(start: date) -> date:
    try:
        return start.replace(year=start.year + 1) - timedelta(days=1)
    except ValueError:  # 29 February
        return start.replace(year=start.year + 1, day=28)


def _round(amount: Decimal, currency: str) -> Decimal:
    return Money(amount, currency).rounded().amount


async def _payments(session: AsyncSession, policy_id: uuid.UUID) -> list[PolicyPayment]:
    stmt = (
        select(PolicyPayment)
        .where(PolicyPayment.policy_id == policy_id)
        .order_by(PolicyPayment.paid_on, PolicyPayment.id)
    )
    return list((await session.scalars(stmt)).all())


async def _paid_by_policy(session: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
    if not ids:
        return {}
    rows = await session.execute(
        select(PolicyPayment.policy_id, func.sum(PolicyPayment.amount))
        .where(PolicyPayment.policy_id.in_(ids), PolicyPayment.voided_at.is_(None))
        .group_by(PolicyPayment.policy_id)
    )
    return {pid: Decimal(total) for pid, total in rows}


def _whatsapp_url(phone: str | None, text_: str) -> str | None:
    return f"https://wa.me/{phone.lstrip('+')}?text={urlquote(text_)}" if phone else None


def _renewal_text(client: clients.Client, policy: Policy, agent: str, agency: str) -> str:
    first = client.first_name or client.display_name
    return (
        f"Hello {first}, your {policy.insurer_name} cover for {policy.description} expires on "
        f"{policy.end_date:%d %b %Y}. Shall I prepare your renewal so you stay covered? "
        f"{agent}, {agency}"
    )


async def _client(session: AsyncSession, client_id: uuid.UUID) -> clients.Client:
    return (
        await session.scalars(select(clients.Client).where(clients.Client.id == client_id))
    ).one()


def _summary(policy: Policy, client: clients.Client, paid: Decimal, today: date) -> dict[str, Any]:
    total = _round(policy.total_premium, policy.currency)
    paid = _round(paid, policy.currency)
    return {
        "id": policy.id,
        "client": quotes.ClientRef(
            id=client.id, display_name=client.display_name, email=client.email, phone=client.phone
        ),
        "policy_number": policy.policy_number,
        "insurer_name": policy.insurer_name,
        "product_name": policy.product_name,
        "class_code": policy.class_code,
        "description": policy.description,
        "status": effective_status(policy, today),
        "start_date": policy.start_date,
        "end_date": policy.end_date,
        "days_to_expiry": (policy.end_date - today).days,
        "currency": policy.currency,
        "total_premium": total,
        "paid": paid,
        "balance": max(total - paid, Decimal(0)),
        "collection_mode": policy.collection_mode,
        "renewal_stage": policy.renewal_stage,
        "owner_user_id": policy.owner_user_id,
    }


async def to_out(ctx: TenantContext, policy: Policy) -> PolicyOut:
    payments = await _payments(ctx.session, policy.id)
    live = [p for p in payments if p.voided_at is None]
    paid = sum((p.amount for p in live), Decimal(0))
    unremitted = sum(
        (p.amount for p in live if p.paid_to == "agent" and p.remitted_on is None), Decimal(0)
    )
    today = await _today(ctx.session, ctx.tenant_id)
    pack, _, _ = await insurers.agency_pack(ctx)
    client = await _client(ctx.session, policy.client_id)
    return PolicyOut(
        **_summary(policy, client, paid, today),
        quote_id=policy.quote_id,
        product_id=policy.product_id,
        details=policy.details,  # type: ignore[arg-type]
        sum_insured=policy.sum_insured,
        breakdown=policy.breakdown,
        commission=policy.commission if insurers.can_see_commission(ctx) else None,
        activated_at=policy.activated_at,
        activation=policy.activation,
        cancelled_at=policy.cancelled_at,
        cancel_reason=policy.cancel_reason,
        renewed_from_id=policy.renewed_from_id,
        renewed_to_id=policy.renewed_to_id,
        renewal_quote_id=policy.renewal_quote_id,
        lost_reason=policy.lost_reason,
        last_contacted_at=policy.last_contacted_at,
        notes=policy.notes,
        payments=[
            PaymentOut(
                id=p.id,
                amount=_round(p.amount, p.currency),
                currency=p.currency,
                paid_on=p.paid_on,
                method=p.method,
                reference=p.reference,
                paid_to=p.paid_to,
                remitted_on=p.remitted_on,
                remittance_reference=p.remittance_reference,
                voided_at=p.voided_at,
                void_reason=p.void_reason,
                created_by=p.created_by,
                created_at=p.created_at,
            )
            for p in payments
        ],
        unremitted=_round(unremitted, policy.currency),
        premium_exceptions=[
            PremiumExceptionOut(id=e.id, name=e.name, source=e.source, note=e.note)
            for e in pack.premium_exceptions_for(policy.class_code, today)
        ],
        version=policy.version,
        created_at=policy.created_at,
    )


async def list_policies(
    ctx: TenantContext,
    *,
    client_id: uuid.UUID | None,
    status: str | None,
    q: str | None,
    expiring_within: int | None,
    limit: int,
) -> list[PolicySummary]:
    today = await _today(ctx.session, ctx.tenant_id)
    stmt = _scoped(select(Policy), ctx)
    if client_id is not None:
        stmt = stmt.where(Policy.client_id == client_id)
    if status == EXPIRED:
        stmt = stmt.where(Policy.status == ACTIVE, Policy.end_date < today)
    elif status == ACTIVE:
        stmt = stmt.where(Policy.status == ACTIVE, Policy.end_date >= today)
    elif status in {PENDING, CANCELLED}:
        stmt = stmt.where(Policy.status == status)
    if expiring_within is not None:
        stmt = stmt.where(
            Policy.status == ACTIVE,
            Policy.end_date.between(today, today + timedelta(days=expiring_within)),
        )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Policy.policy_number.ilike(like),
                Policy.description.ilike(like),
                Policy.insurer_name.ilike(like),
            )
        )
    order = Policy.end_date.asc() if expiring_within is not None else Policy.id.desc()
    rows = list((await ctx.session.scalars(stmt.order_by(order).limit(limit))).all())
    paid = await _paid_by_policy(ctx.session, [p.id for p in rows])
    return [
        PolicySummary(
            **_summary(
                p, await _client(ctx.session, p.client_id), paid.get(p.id, Decimal(0)), today
            )
        )
        for p in rows
    ]


# ---------------------------------------------------------------- create


def _describe(details: list[dict[str, str]], fallback: str) -> str:
    return details[0]["value"][:200] if details else fallback


async def _finish_create(
    ctx: TenantContext, policy: Policy, body: FromQuote | PolicyCreate, source: str
) -> Policy:
    ctx.session.add(policy)
    await ctx.session.flush()
    if policy.renewed_from_id is not None:
        previous = await get_policy(ctx, policy.renewed_from_id, lock=True)
        previous.renewal_stage, previous.renewed_to_id = "renewed", policy.id
    if body.payment is not None:
        await _add_payment(ctx, policy, body.payment)
    await audit.record(
        ctx,
        "policy.created",
        entity_type="policy",
        entity_id=policy.id,
        changes={"client_id": str(policy.client_id), "source": source},
    )
    if body.insurer_confirmed:
        paid = (await _paid_by_policy(ctx.session, [policy.id])).get(policy.id, Decimal(0))
        if paid >= policy.total_premium:
            await _activate(ctx, policy, Activate(insurer_confirmed=True), paid)
    await ctx.session.flush()
    await ctx.session.refresh(policy)
    return policy


async def create_from_quote(ctx: TenantContext, body: FromQuote) -> Policy:
    existing = await ctx.session.scalar(select(Policy.id).where(Policy.quote_id == body.quote_id))
    if existing is not None:
        raise PolicyExistsError(f"Policy {existing} was already created from this quote")
    quote, option = await quotes.take_up(ctx, body.quote_id, body.option)
    previous = await ctx.session.scalar(
        select(Policy).where(Policy.renewal_quote_id == quote.id, Policy.renewed_to_id.is_(None))
    )
    details = [d.model_dump() for d in body.details] if body.details is not None else quote.details
    sum_insured = quote.risk.get("sum_insured")
    policy = Policy(
        tenant_id=ctx.tenant_id,
        client_id=quote.client_id,
        owner_user_id=quote.owner_user_id,
        quote_id=quote.id,
        product_id=option.product_id,
        insurer_name=option.insurer_name,
        product_name=option.product_name,
        class_code=quote.class_code,
        policy_number=body.policy_number,
        description=_describe(details, quote.title),
        details=details,
        start_date=body.start_date,
        end_date=body.end_date or _year_end(body.start_date),
        currency=quote.currency,
        sum_insured=Decimal(sum_insured) if sum_insured else None,
        total_premium=option.client_total,
        breakdown=option.breakdown,
        commission=option.commission,
        collection_mode=body.collection_mode,
        renewed_from_id=previous.id if previous is not None else None,
        notes=body.notes,
        created_by=ctx.principal.user_id,
        updated_by=ctx.principal.user_id,
    )
    return await _finish_create(ctx, policy, body, "quote")


async def create_policy(ctx: TenantContext, body: PolicyCreate) -> Policy:
    client = await clients.get_visible_client(ctx, body.client_id)
    pack, _, _ = await insurers.agency_pack(ctx)
    tenant = await tenancy.get_tenant(ctx.session, ctx.tenant_id)
    insurer_name, product_name, class_code = body.insurer_name, body.product_name, body.class_code
    currency = tenant.default_currency
    if body.product_id is not None:
        product = await insurers.get_product(ctx, body.product_id)
        insurer = await insurers.get_insurer(ctx, product.insurer_id)
        insurer_name, product_name = insurer.name, product.name
        class_code, currency = product.class_code, product.currency
    if not insurer_name or not class_code:
        raise AppError("Choose a product, or enter the insurer and class of business")
    klass = pack.insurance_class(class_code)
    if klass is None:
        raise insurers.UnknownClassError(f"Unknown class of business {class_code!r}")
    if body.renewed_from_id is not None:
        previous = await get_policy(ctx, body.renewed_from_id)
        if previous.renewed_to_id is not None:
            raise PolicyStateError("That policy has already been renewed")
        if previous.client_id != client.id:
            raise AppError("A renewal must be for the same client")
    details = [d.model_dump() for d in body.details or []]
    policy = Policy(
        tenant_id=ctx.tenant_id,
        client_id=client.id,
        owner_user_id=client.owner_user_id or ctx.principal.user_id,
        product_id=body.product_id,
        insurer_name=insurer_name,
        product_name=product_name or klass.name,
        class_code=class_code,
        policy_number=body.policy_number,
        description=body.description or _describe(details, klass.name),
        details=details,
        start_date=body.start_date,
        end_date=body.end_date or _year_end(body.start_date),
        currency=currency,
        sum_insured=body.sum_insured,
        total_premium=body.total_premium,
        collection_mode=body.collection_mode,
        renewed_from_id=body.renewed_from_id,
        notes=body.notes,
        created_by=ctx.principal.user_id,
        updated_by=ctx.principal.user_id,
    )
    return await _finish_create(ctx, policy, body, "manual")


# ---------------------------------------------------------------- edit / activate / cancel


async def update_policy(
    ctx: TenantContext, policy_id: uuid.UUID, body: PolicyUpdate, if_match: str | None
) -> Policy:
    policy = await get_policy(ctx, policy_id)
    check_version(if_match, policy.version)
    data = body.model_dump(exclude_unset=True)
    if ({"start_date", "end_date"} & data.keys()) and policy.status != PENDING:
        raise PolicyStateError("Dates can only change before the policy is active")
    start = data.get("start_date") or policy.start_date
    end = data.get("end_date") or policy.end_date
    if end <= start:
        raise AppError("The end date must be after the start date")
    if "details" in data and data["details"] is not None:
        data["details"] = [dict(d) for d in data["details"]]
    for field, value in data.items():
        if value is not None or field in {"policy_number", "notes"}:
            setattr(policy, field, value)
    policy.updated_by = ctx.principal.user_id
    await ctx.session.flush()
    await ctx.session.refresh(policy)
    return policy


async def _activate(ctx: TenantContext, policy: Policy, body: Activate, paid: Decimal) -> None:
    evidence: dict[str, Any] = {
        "basis": body.basis,
        "insurer_confirmed": True,
        "paid": str(_round(paid, policy.currency)),
        "by": ctx.principal.user_id,
        "note": body.note,
    }
    if body.basis == "paid":
        if paid < policy.total_premium:
            raise PremiumNotPaidError(
                f"{_round(paid, policy.currency)} of {_round(policy.total_premium, policy.currency)} "
                f"{policy.currency} has been recorded"
            )
    else:
        pack, code, version = await insurers.agency_pack(ctx)
        allowed = {
            e.id: e
            for e in pack.premium_exceptions_for(
                policy.class_code, await _today(ctx.session, ctx.tenant_id)
            )
        }
        exception = allowed.get(body.exception_id or "")
        if exception is None:
            raise PremiumNotPaidError("That exception does not apply to this class of business")
        evidence |= {
            "exception_id": exception.id,
            "exception": exception.name,
            "source": exception.source,
            "pack": f"{code}/{version}",
        }
    policy.status, policy.activated_at, policy.activation = ACTIVE, datetime.now(UTC), evidence
    await audit.record(
        ctx, "policy.activated", entity_type="policy", entity_id=policy.id, changes=evidence
    )


async def activate(ctx: TenantContext, policy_id: uuid.UUID, body: Activate) -> Policy:
    policy = await get_policy(ctx, policy_id, lock=True)
    if policy.status != PENDING:
        raise PolicyStateError(f"A {policy.status} policy cannot be activated")
    paid = (await _paid_by_policy(ctx.session, [policy.id])).get(policy.id, Decimal(0))
    await _activate(ctx, policy, body, paid)
    policy.updated_by = ctx.principal.user_id
    await ctx.session.flush()
    await ctx.session.refresh(policy)
    return policy


async def cancel(ctx: TenantContext, policy_id: uuid.UUID, body: Cancel) -> Policy:
    policy = await get_policy(ctx, policy_id, lock=True)
    if policy.status == CANCELLED:
        raise PolicyStateError("The policy is already cancelled")
    policy.status, policy.cancelled_at, policy.cancel_reason = (
        CANCELLED,
        datetime.now(UTC),
        body.reason,
    )
    policy.updated_by = ctx.principal.user_id
    await audit.record(
        ctx,
        "policy.cancelled",
        entity_type="policy",
        entity_id=policy.id,
        changes={"reason": body.reason},
    )
    await ctx.session.flush()
    await ctx.session.refresh(policy)
    return policy


# ---------------------------------------------------------------- payments


async def _add_payment(ctx: TenantContext, policy: Policy, body: PaymentIn) -> PolicyPayment:
    paid_to = body.paid_to or (
        "agent" if policy.collection_mode == "agent_collected" else "insurer"
    )
    payment = PolicyPayment(
        tenant_id=ctx.tenant_id,
        policy_id=policy.id,
        amount=body.amount,
        currency=policy.currency,
        paid_on=body.paid_on,
        method=body.method,
        reference=body.reference,
        paid_to=paid_to,
        created_by=ctx.principal.user_id,
    )
    ctx.session.add(payment)
    await ctx.session.flush()
    if paid_to == "agent":
        # Regs r.42: premium an agent receives is remitted to the insurer immediately.
        tenant = await tenancy.get_tenant(ctx.session, ctx.tenant_id)
        zone = ZoneInfo(tenant.timezone)
        due = datetime.combine(datetime.now(zone).date(), time(17, 0), zone)
        members = {
            m.auth_user_id for m in await tenancy.list_members(ctx.session) if m.status == "active"
        }
        assignee = (
            policy.owner_user_id if policy.owner_user_id in members else ctx.principal.user_id
        )
        task = await tasks.create_task(
            ctx,
            tasks.TaskCreate(
                title=(
                    f"Remit {policy.currency} {_round(body.amount, policy.currency):,} to "
                    f"{policy.insurer_name} ({policy.description})"[:200]
                ),
                notes="Premium received by the agency must be remitted to the insurer immediately (Regs r.42).",
                due_at=due,
                assignee_user_id=assignee,
                priority="high",
                entity_type="policy",
                entity_id=policy.id,
            ),
        )
        payment.remit_task_id = task.id
    await audit.record(
        ctx,
        "policy.payment_recorded",
        entity_type="policy",
        entity_id=policy.id,
        changes={"amount": str(body.amount), "paid_to": paid_to, "reference": body.reference or ""},
    )
    return payment


async def record_payment(ctx: TenantContext, policy_id: uuid.UUID, body: PaymentIn) -> Policy:
    policy = await get_policy(ctx, policy_id, lock=True)
    if policy.status == CANCELLED:
        raise PolicyStateError("Payments cannot be recorded on a cancelled policy")
    await _add_payment(ctx, policy, body)
    await ctx.session.flush()
    return policy


async def _payment(ctx: TenantContext, policy: Policy, payment_id: uuid.UUID) -> PolicyPayment:
    payment = await ctx.session.scalar(
        select(PolicyPayment)
        .where(PolicyPayment.id == payment_id, PolicyPayment.policy_id == policy.id)
        .with_for_update()
    )
    if payment is None:
        raise NotFoundError("Payment not found")
    if payment.voided_at is not None:
        raise PolicyStateError("The payment was voided")
    return payment


async def void_payment(
    ctx: TenantContext, policy_id: uuid.UUID, payment_id: uuid.UUID, body: VoidPayment
) -> Policy:
    policy = await get_policy(ctx, policy_id, lock=True)
    payment = await _payment(ctx, policy, payment_id)
    payment.voided_at, payment.void_reason, payment.voided_by = (
        datetime.now(UTC),
        body.reason,
        ctx.principal.user_id,
    )
    if payment.remit_task_id is not None and payment.remitted_on is None:
        await tasks.complete_task(ctx, payment.remit_task_id)
    await audit.record(
        ctx,
        "policy.payment_voided",
        entity_type="policy",
        entity_id=policy.id,
        changes={"payment_id": str(payment.id), "reason": body.reason},
    )
    await ctx.session.flush()
    return policy


async def mark_remitted(
    ctx: TenantContext, policy_id: uuid.UUID, payment_id: uuid.UUID, body: Remitted
) -> Policy:
    policy = await get_policy(ctx, policy_id, lock=True)
    payment = await _payment(ctx, policy, payment_id)
    if payment.paid_to != "agent":
        raise PolicyStateError("Only premium the agency received is remitted")
    if payment.remitted_on is not None:
        raise PolicyStateError("The payment was already remitted")
    payment.remitted_on, payment.remittance_reference = body.remitted_on, body.reference
    if payment.remit_task_id is not None:
        await tasks.complete_task(ctx, payment.remit_task_id)
    await audit.record(
        ctx,
        "policy.premium_remitted",
        entity_type="policy",
        entity_id=policy.id,
        changes={"payment_id": str(payment.id), "reference": body.reference or ""},
    )
    await ctx.session.flush()
    return policy


# ---------------------------------------------------------------- renewals


async def _agent(session: AsyncSession, user_id: str) -> tuple[str, str | None]:
    member = next(
        (m for m in await tenancy.list_members(session) if m.auth_user_id == user_id), None
    )
    return (member.name or member.email, member.phone) if member else ("", None)


async def renewal_board(ctx: TenantContext, *, window_days: int, owner: str | None) -> RenewalBoard:
    today = await _today(ctx.session, ctx.tenant_id)
    tenant = await tenancy.get_tenant(ctx.session, ctx.tenant_id)
    stmt = _scoped(select(Policy), ctx).where(
        Policy.status == ACTIVE,
        Policy.end_date.between(today - timedelta(days=30), today + timedelta(days=window_days)),
    )
    if owner:
        stmt = stmt.where(Policy.owner_user_id == owner)
    rows = list((await ctx.session.scalars(stmt.order_by(Policy.end_date).limit(500))).all())
    paid = await _paid_by_policy(ctx.session, [p.id for p in rows])
    quote_status = await quotes.statuses(
        ctx, [p.renewal_quote_id for p in rows if p.renewal_quote_id]
    )
    agents: dict[str, str] = {}
    items: list[RenewalItem] = []
    for policy in rows:
        client = await _client(ctx.session, policy.client_id)
        if policy.owner_user_id not in agents:
            agents[policy.owner_user_id] = (await _agent(ctx.session, policy.owner_user_id))[0]
        message = _renewal_text(client, policy, agents[policy.owner_user_id], tenant.name)
        items.append(
            RenewalItem(
                **_summary(policy, client, paid.get(policy.id, Decimal(0)), today),
                whatsapp_url=_whatsapp_url(client.phone, message),
                last_contacted_at=policy.last_contacted_at,
                renewal_quote_id=policy.renewal_quote_id,
                renewal_quote_status=quote_status.get(policy.renewal_quote_id)
                if policy.renewal_quote_id
                else None,
                lost_reason=policy.lost_reason,
            )
        )
    columns = []
    for stage in STAGES:
        in_stage = [i for i in items if i.renewal_stage == stage]
        premium = sum(
            (i.total_premium for i in in_stage if i.currency == tenant.default_currency), Decimal(0)
        )
        columns.append(RenewalColumn(stage=stage, count=len(in_stage), premium=premium))  # type: ignore[arg-type]
    return RenewalBoard(
        window_days=window_days, currency=tenant.default_currency, columns=columns, items=items
    )


async def update_renewal(ctx: TenantContext, policy_id: uuid.UUID, body: RenewalUpdate) -> Policy:
    policy = await get_policy(ctx, policy_id, lock=True)
    if policy.renewal_stage == "renewed":
        raise PolicyStateError("The policy has already been renewed")
    if body.stage == "lost" and not body.lost_reason:
        raise ReasonRequiredError("For example: price, sold the car, went direct to the insurer")
    policy.renewal_stage = body.stage
    policy.lost_reason = body.lost_reason if body.stage == "lost" else None
    if body.stage == "contacted":
        policy.last_contacted_at = datetime.now(UTC)
    if body.note:
        await clients.add_activity(
            ctx,
            policy.client_id,
            clients.ActivityIn(kind="note", body=f"Renewal of {policy.description}: {body.note}"),
        )
    await audit.record(
        ctx,
        "policy.renewal_stage",
        entity_type="policy",
        entity_id=policy.id,
        changes={"stage": body.stage, "lost_reason": body.lost_reason or ""},
    )
    policy.updated_by = ctx.principal.user_id
    await ctx.session.flush()
    await ctx.session.refresh(policy)
    return policy


async def remind(
    ctx: TenantContext, policy_id: uuid.UUID, body: Remind
) -> tuple[Policy, str | None, str | None]:
    """Contact the client about the renewal now: email it, or open WhatsApp; either way, log it."""
    policy = await get_policy(ctx, policy_id, lock=True)
    if policy.status != ACTIVE or policy.renewal_stage in CLOSED_STAGES:
        raise PolicyStateError("Only active policies that are not yet renewed can be reminded")
    client = await clients.get_visible_client(ctx, policy.client_id)
    tenant = await tenancy.get_tenant(ctx.session, ctx.tenant_id)
    agent_name, agent_phone = await _agent(ctx.session, ctx.principal.user_id)
    message = body.message or _renewal_text(client, policy, agent_name, tenant.name)
    whatsapp, emailed = None, None
    if body.channel == "email":
        if not client.email:
            raise AppError("The client has no email address; send a WhatsApp message instead")
        await messaging.queue_email(
            ctx.session,
            tenant_id=ctx.tenant_id,
            event="policy.renewal_due",
            to=client.email,
            context=_email_context(
                client,
                policy=policy,
                tenant=tenant,
                agent_name=agent_name,
                agent_phone=agent_phone,
                message=body.message,
            ),
            entity_type="policy",
            entity_id=policy.id,
            actor=ctx.principal.user_id,
        )
        emailed = client.email
    elif body.channel == "whatsapp":
        whatsapp = _whatsapp_url(client.phone, message)
        if whatsapp is None:
            raise AppError("The client has no phone number")
    await clients.add_activity(
        ctx,
        client.id,
        clients.ActivityIn(
            kind=body.channel,
            body=f"Renewal reminder for {policy.description} (expires {policy.end_date:%d %b %Y})",
        ),
    )
    policy.last_contacted_at = datetime.now(UTC)
    if policy.renewal_stage == "due":
        policy.renewal_stage = "contacted"
    await ctx.session.flush()
    await ctx.session.refresh(policy)
    return policy, whatsapp, emailed


def _email_context(
    client: clients.Client,
    *,
    policy: Policy,
    tenant: Any,
    agent_name: str,
    agent_phone: str | None,
    message: str | None,
) -> dict[str, str]:
    return {
        "recipient_name": client.first_name or client.display_name,
        "tenant_name": tenant.name,
        "agent_name": agent_name or tenant.name,
        "agent_phone": agent_phone or tenant.phone or "",
        "insurer_name": policy.insurer_name,
        "policy_description": policy.description,
        "expires_on": f"{policy.end_date:%d %b %Y}",
        "message": message or "",
    }


async def renewal_quote(
    ctx: TenantContext, policy_id: uuid.UUID, body: RenewalQuote
) -> quotes.Quote:
    policy = await get_policy(ctx, policy_id, lock=True)
    if policy.status != ACTIVE or policy.renewal_stage in CLOSED_STAGES:
        raise PolicyStateError("Only active policies that are not yet renewed can be re-quoted")
    details = [quotes.Detail.model_validate(d) for d in policy.details]
    quote = await quotes.create_quote(
        ctx, body.to_quote(policy.client_id, details, f"Renewal: {policy.description}"[:120])
    )
    policy.renewal_quote_id, policy.renewal_stage = quote.id, "quoted"
    policy.updated_by = ctx.principal.user_id
    await ctx.session.flush()
    return quote


async def counts(ctx: TenantContext) -> dict[str, int]:
    """Dashboard: active policies, renewals due in 30 days, premium payments waiting to be remitted."""
    today = await _today(ctx.session, ctx.tenant_id)
    base = _scoped(select(func.count()).select_from(Policy), ctx)
    active = base.where(Policy.status == ACTIVE, Policy.end_date >= today)
    due = active.where(
        Policy.end_date <= today + timedelta(days=30),
        Policy.renewal_stage.not_in(CLOSED_STAGES),
    )
    unremitted = _scoped(
        select(func.count())
        .select_from(PolicyPayment)
        .join(Policy, Policy.id == PolicyPayment.policy_id)
        .where(
            PolicyPayment.paid_to == "agent",
            PolicyPayment.remitted_on.is_(None),
            PolicyPayment.voided_at.is_(None),
        ),
        ctx,
    )
    return {
        "active": int(await ctx.session.scalar(active) or 0),
        "renewals_due_30d": int(await ctx.session.scalar(due) or 0),
        "premiums_to_remit": int(await ctx.session.scalar(unremitted) or 0),
    }


# ---------------------------------------------------------------- reminder jobs


async def enqueue_renewal_reminders(session: AsyncSession) -> int:
    """Cross-tenant scan through the narrow SECURITY DEFINER function, then one job per reminder."""
    rows = (
        await session.execute(
            text(
                "SELECT tenant_id, policy_id, offset_days FROM app.policies_due_for_renewal_reminder()"
            )
        )
    ).all()
    for tenant_id, policy_id, offset in rows:
        await events.enqueue(
            session,
            REMIND_RENEWAL,
            {"tenant_id": str(tenant_id), "policy_id": str(policy_id), "offset_days": offset},
            queueing_lock=f"renewal:{policy_id}:{offset}",
        )
    return len(rows)


async def send_renewal_reminder(
    session: AsyncSession,
    settings: Settings,
    tenant_id: uuid.UUID,
    policy_id: uuid.UUID,
    offset_days: int,
) -> bool:
    """Remind the owner (and, if the agency allows, email the client) once per offset. Idempotent."""
    policy = await session.get(Policy, policy_id, with_for_update=True)
    if policy is None or policy.status != ACTIVE or policy.renewal_stage in CLOSED_STAGES:
        return False
    tenant = await tenancy.get_tenant(session, tenant_id)
    client = await _client(session, policy.client_id)
    emailed = client.email if tenant.renewal_client_emails and client.email else None
    inserted = await session.scalar(
        insert(RenewalReminder)
        .values(
            tenant_id=tenant_id, policy_id=policy.id, offset_days=offset_days, emailed_to=emailed
        )
        .on_conflict_do_nothing()
        .returning(RenewalReminder.id)
    )
    if inserted is None:
        return False
    days = (policy.end_date - datetime.now(ZoneInfo(tenant.timezone)).date()).days
    when = "today" if days == 0 else f"in {days} day{'s' if days != 1 else ''}"
    await notifications.notify(
        session,
        settings,
        tenant_id=tenant_id,
        user_ids=[policy.owner_user_id],
        kind="policy.renewal_due",
        title=f"{client.display_name}: {policy.description} expires {when}",
        body=f"{policy.insurer_name} {policy.product_name}, ends {policy.end_date:%d %b %Y}.",
        link=f"/renewals?focus={policy.id}",
    )
    if emailed:
        agent_name, agent_phone = await _agent(session, policy.owner_user_id)
        await messaging.queue_email(
            session,
            tenant_id=tenant_id,
            event="policy.renewal_due",
            to=emailed,
            context=_email_context(
                client,
                policy=policy,
                tenant=tenant,
                agent_name=agent_name,
                agent_phone=agent_phone,
                message=None,
            ),
            entity_type="policy",
            entity_id=policy.id,
        )
    return True
