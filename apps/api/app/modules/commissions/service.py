"""Commission tracking (Plan A1.1 R1.5): expected vs received, with the WHT insurers withhold.

**Expected** commission lives on each policy (from the quote's calculation, or set by hand). **Received**
commission is recorded as a receipt from an insurer (often a monthly payment with a statement) split into
allocations, one per policy. WHT defaults to the pack rate for the agency (10% for resident agents in Kenya),
but the figure on the insurer's statement wins when entered. Receipts are voided, never edited or deleted.

Members with ``commission:read:own`` see only their own policies' figures (computed from allocations);
``commission:read:all`` also sees whole receipts and WHT certificates.
"""

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from http import HTTPStatus

from sqlalchemy import select

from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.money import Money
from app.core.permissions import Perm
from app.modules.commissions.models import CommissionAllocation, CommissionReceipt
from app.modules.commissions.schemas import (
    AllocationOut,
    Amounts,
    InsurerRow,
    MonthRow,
    ReceiptCreate,
    ReceiptOut,
    Statement,
    StatementRow,
    Summary,
    VoidReceipt,
    WhtCertificate,
)
from app.modules.insurers import service as insurers
from app.modules.policies import service as policies
from app.modules.tenancy import service as tenancy
from app.platform import audit
from app.platform.deps import TenantContext

ZERO = Decimal(0)


class ReceiptError(AppError):
    status = HTTPStatus.UNPROCESSABLE_CONTENT
    code = "commission_receipt_invalid"
    title = "The commission receipt does not match the policies"


def _sees_all(ctx: TenantContext) -> bool:
    return Perm.COMMISSION_READ_ALL in ctx.principal.permissions


def _round(amount: Decimal, currency: str) -> Decimal:
    return Money(amount, currency).rounded().amount


async def _received(
    ctx: TenantContext, policy_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[tuple[CommissionAllocation, CommissionReceipt]]]:
    if not policy_ids:
        return {}
    rows = await ctx.session.execute(
        select(CommissionAllocation, CommissionReceipt)
        .join(CommissionReceipt, CommissionReceipt.id == CommissionAllocation.receipt_id)
        .where(
            CommissionAllocation.policy_id.in_(policy_ids), CommissionReceipt.voided_at.is_(None)
        )
    )
    out: dict[uuid.UUID, list[tuple[CommissionAllocation, CommissionReceipt]]] = defaultdict(list)
    for allocation, receipt in rows:
        out[allocation.policy_id].append((allocation, receipt))
    return out


def _expected(entry: policies.BookEntry) -> tuple[Decimal, Decimal, Decimal]:
    c = entry.commission or {}
    return (
        Decimal(str(c.get("gross", 0))),
        Decimal(str(c.get("wht", 0))),
        Decimal(str(c.get("net", 0))),
    )


def _amounts(gross: Decimal, wht: Decimal, net: Decimal, currency: str) -> Amounts:
    return Amounts(
        gross=_round(gross, currency), wht=_round(wht, currency), net=_round(net, currency)
    )


# ---------------------------------------------------------------- statement


async def statement(
    ctx: TenantContext,
    *,
    insurer: str | None,
    policy_id: uuid.UUID | None,
    outstanding_only: bool,
) -> Statement:
    tenant = await tenancy.get_tenant(ctx.session, ctx.tenant_id)
    book = await policies.commission_book(
        ctx, insurer=insurer, policy_ids=[policy_id] if policy_id else None
    )
    received = await _received(ctx, [b.id for b in book])
    rows: list[StatementRow] = []
    for entry in book:
        eg, ew, en = _expected(entry)
        got = received.get(entry.id, [])
        rg = sum((a.gross for a, _ in got), ZERO)
        rw = sum((a.wht for a, _ in got), ZERO)
        rn = sum((a.net for a, _ in got), ZERO)
        if outstanding_only and en - rn <= 0:
            continue
        rate = (entry.commission or {}).get("rate")
        rows.append(
            StatementRow(
                policy_id=entry.id,
                client_name=entry.client_name,
                description=entry.description,
                insurer_name=entry.insurer_name,
                policy_number=entry.policy_number,
                start_date=entry.start_date,
                status=entry.status,
                currency=entry.currency,
                rate=str(rate) if rate is not None else None,
                expected=_amounts(eg, ew, en, entry.currency),
                received=_amounts(rg, rw, rn, entry.currency),
                outstanding=_amounts(eg - rg, ew - rw, en - rn, entry.currency),
            )
        )
    currency = tenant.default_currency
    mine = [r for r in rows if r.currency == currency]
    return Statement(
        currency=currency,
        rows=rows,
        expected_net=sum((r.expected.net for r in mine), ZERO),
        received_net=sum((r.received.net for r in mine), ZERO),
        outstanding_net=sum((r.outstanding.net for r in mine), ZERO),
    )


# ---------------------------------------------------------------- receipts


async def _receipt_out(ctx: TenantContext, receipt: CommissionReceipt) -> ReceiptOut:
    allocations = list(
        (
            await ctx.session.scalars(
                select(CommissionAllocation).where(CommissionAllocation.receipt_id == receipt.id)
            )
        ).all()
    )
    book = {
        b.id: b
        for b in await policies.commission_book(ctx, policy_ids=[a.policy_id for a in allocations])
    }
    c = receipt.currency
    return ReceiptOut(
        id=receipt.id,
        insurer_name=receipt.insurer_name,
        received_on=receipt.received_on,
        currency=c,
        gross=_round(receipt.gross, c),
        wht=_round(receipt.wht, c),
        vat=_round(receipt.vat, c),
        net=_round(receipt.net, c),
        reference=receipt.reference,
        wht_certificate=receipt.wht_certificate,
        notes=receipt.notes,
        voided_at=receipt.voided_at,
        void_reason=receipt.void_reason,
        created_by=receipt.created_by,
        created_at=receipt.created_at,
        lines=[
            AllocationOut(
                policy_id=a.policy_id,
                client_name=book[a.policy_id].client_name if a.policy_id in book else "",
                description=book[a.policy_id].description if a.policy_id in book else "",
                policy_number=book[a.policy_id].policy_number if a.policy_id in book else None,
                gross=_round(a.gross, c),
                wht=_round(a.wht, c),
                vat=_round(a.vat, c),
                net=_round(a.net, c),
            )
            for a in allocations
        ],
    )


async def record_receipt(ctx: TenantContext, body: ReceiptCreate) -> ReceiptOut:
    ids = [line.policy_id for line in body.lines]
    if len(set(ids)) != len(ids):
        raise ReceiptError("Each policy can appear once on a receipt")
    book = {b.id: b for b in await policies.commission_book(ctx, policy_ids=ids)}
    missing = [str(i) for i in ids if i not in book]
    if missing:
        raise NotFoundError(
            "Some policies were not found, are cancelled, or have no expected commission"
        )
    currencies = {book[i].currency for i in ids}
    if len(currencies) != 1:
        raise ReceiptError("All policies on a receipt must be in the same currency")
    currency = currencies.pop()
    receipt = CommissionReceipt(
        tenant_id=ctx.tenant_id,
        insurer_name=body.insurer_name,
        received_on=body.received_on,
        currency=currency,
        gross=ZERO,
        wht=ZERO,
        vat=ZERO,
        net=ZERO,
        reference=body.reference,
        wht_certificate=body.wht_certificate,
        notes=body.notes,
        created_by=ctx.principal.user_id,
    )
    ctx.session.add(receipt)
    await ctx.session.flush()
    for line in body.lines:
        w = await insurers.withholding_for(ctx, line.gross, currency)
        wht = _round(line.wht, currency) if line.wht is not None else w.wht
        if wht > w.gross:
            raise ReceiptError("WHT cannot be more than the gross commission")
        net = w.gross - wht + w.vat
        ctx.session.add(
            CommissionAllocation(
                tenant_id=ctx.tenant_id,
                receipt_id=receipt.id,
                policy_id=line.policy_id,
                gross=w.gross,
                wht=wht,
                vat=w.vat,
                net=net,
            )
        )
        receipt.gross += w.gross
        receipt.wht += wht
        receipt.vat += w.vat
        receipt.net += net
    await ctx.session.flush()
    await audit.record(
        ctx,
        "commission.received",
        entity_type="commission_receipt",
        entity_id=receipt.id,
        changes={"insurer": body.insurer_name, "net": str(receipt.net), "policies": len(ids)},
    )
    return await _receipt_out(ctx, receipt)


async def list_receipts(ctx: TenantContext, *, year: int | None, limit: int) -> list[ReceiptOut]:
    stmt = select(CommissionReceipt).order_by(
        CommissionReceipt.received_on.desc(), CommissionReceipt.id.desc()
    )
    if year is not None:
        stmt = stmt.where(
            CommissionReceipt.received_on.between(date(year, 1, 1), date(year, 12, 31))
        )
    return [
        await _receipt_out(ctx, r) for r in (await ctx.session.scalars(stmt.limit(limit))).all()
    ]


async def void_receipt(ctx: TenantContext, receipt_id: uuid.UUID, body: VoidReceipt) -> ReceiptOut:
    receipt = await ctx.session.scalar(
        select(CommissionReceipt).where(CommissionReceipt.id == receipt_id).with_for_update()
    )
    if receipt is None:
        raise NotFoundError("Commission receipt not found")
    if receipt.voided_at is not None:
        raise ConflictError("The receipt was already voided")
    receipt.voided_at, receipt.void_reason, receipt.voided_by = (
        datetime.now(UTC),
        body.reason,
        ctx.principal.user_id,
    )
    await audit.record(
        ctx,
        "commission.voided",
        entity_type="commission_receipt",
        entity_id=receipt.id,
        changes={"reason": body.reason},
    )
    await ctx.session.flush()
    return await _receipt_out(ctx, receipt)


# ---------------------------------------------------------------- summary


async def summary(ctx: TenantContext, year: int) -> Summary:
    tenant = await tenancy.get_tenant(ctx.session, ctx.tenant_id)
    currency = tenant.default_currency
    first, last = date(year, 1, 1), date(year, 12, 31)
    book = [b for b in await policies.commission_book(ctx) if b.currency == currency]
    received = await _received(ctx, [b.id for b in book])
    months = {f"{year}-{m:02d}": [ZERO, ZERO, ZERO] for m in range(1, 13)}
    insurers_: dict[str, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO, ZERO, ZERO])
    expected_year = received_year = wht_year = outstanding = ZERO
    for entry in book:
        _, _, en = _expected(entry)
        got = received.get(entry.id, [])
        rn_all = sum((a.net for a, _ in got), ZERO)
        outstanding += en - rn_all
        row = insurers_[entry.insurer_name]
        row[2] += en - rn_all
        if first <= entry.start_date <= last:
            expected_year += en
            months[f"{entry.start_date:%Y-%m}"][0] += en
            row[0] += en
        for allocation, receipt in got:
            if first <= receipt.received_on <= last:
                received_year += allocation.net
                wht_year += allocation.wht
                months[f"{receipt.received_on:%Y-%m}"][1] += allocation.net
                months[f"{receipt.received_on:%Y-%m}"][2] += allocation.wht
                row[1] += allocation.net
                row[3] += allocation.wht
    certificates: list[WhtCertificate] = []
    if _sees_all(ctx):
        receipts = await ctx.session.scalars(
            select(CommissionReceipt)
            .where(
                CommissionReceipt.received_on.between(first, last),
                CommissionReceipt.voided_at.is_(None),
                CommissionReceipt.wht > 0,
                CommissionReceipt.currency == currency,
            )
            .order_by(CommissionReceipt.received_on)
        )
        certificates = [
            WhtCertificate(
                receipt_id=r.id,
                insurer_name=r.insurer_name,
                received_on=r.received_on,
                wht=_round(r.wht, currency),
                certificate=r.wht_certificate,
            )
            for r in receipts
        ]

    def money(amount: Decimal) -> Decimal:
        return _round(amount, currency)

    return Summary(
        year=year,
        currency=currency,
        expected_net=money(expected_year),
        received_net=money(received_year),
        outstanding_net=money(outstanding),
        wht=money(wht_year),
        months=[
            MonthRow(month=m, expected_net=money(e), received_net=money(r), wht=money(w))
            for m, (e, r, w) in months.items()
        ],
        insurers=sorted(
            (
                InsurerRow(
                    insurer_name=name,
                    expected_net=money(v[0]),
                    received_net=money(v[1]),
                    outstanding_net=money(v[2]),
                    wht=money(v[3]),
                )
                for name, v in insurers_.items()
            ),
            key=lambda r: r.outstanding_net,
            reverse=True,
        ),
        wht_certificates=certificates,
    )


async def received_since(ctx: TenantContext, since: date) -> Decimal:
    """Net commission received since a date on the policies the member may see (dashboard)."""
    tenant = await tenancy.get_tenant(ctx.session, ctx.tenant_id)
    book = [b for b in await policies.commission_book(ctx) if b.currency == tenant.default_currency]
    received = await _received(ctx, [b.id for b in book])
    total = sum(
        (a.net for got in received.values() for a, r in got if r.received_on >= since), ZERO
    )
    return _round(total, tenant.default_currency)
