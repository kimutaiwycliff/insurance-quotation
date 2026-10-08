"""Invoices, credit notes and payments (Plan A1.2 R2.1; ADR-0009 states, ADR-0012 ledger).

- Drafts are edited freely. Issuing numbers the document, gives an invoice its payment reference, freezes it
  (a database trigger enforces this) and posts the ledger entry.
- Payments are records of money the client paid into the tenant's own account; the platform never holds
  funds. A payment is applied to invoices (explicitly, or oldest first); anything left over is client credit
  that can be applied later. Credit notes work the same way.
- "Paid", "balance" and "overdue" are derived from allocations and the tenant's date, never stored.
"""

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from http import HTTPStatus
from typing import Any, Literal
from urllib.parse import quote as urlquote

from sqlalchemy import Select, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.calc.invoice import InvoiceInputError, LineIn, calculate_invoice
from app.core.concurrency import check_version
from app.core.config import Settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.money import Money
from app.core.permissions import Perm
from app.integrations.pdf import PdfRenderer
from app.integrations.storage.s3 import S3Storage
from app.modules.billing.models import Allocation, BillingDocument, BillingLine, Payment

__all__ = ["BillingDocument"]
from app.modules.billing.schemas import (
    BillingDocumentOut,
    BillingDocumentSummary,
    BillingLineOut,
    ClientAccount,
    CreditNoteCreate,
    InvoiceCreate,
    InvoiceUpdate,
    Issue,
    LineInput,
    PaymentAllocationIn,
    PaymentAllocationOut,
    PaymentCreate,
    ReceivedPayment,
    Send,
    TaxLine,
    Void,
)
from app.modules.catalog import service as catalog
from app.modules.clients import service as clients
from app.modules.documents import service as documents
from app.modules.insurers import service as insurers
from app.modules.ledger import service as ledger
from app.modules.ledger.service import Leg
from app.modules.numbering import service as numbering
from app.modules.public_links import service as links
from app.modules.quotes.service import ClientRef
from app.modules.rendering import service as rendering
from app.modules.rendering.service import (
    AmountLine,
    DocumentView,
    KeyValue,
    LineItem,
    Party,
    PaymentInstructions,
    Totals,
)
from app.modules.tenancy import service as tenancy
from app.platform import audit
from app.platform.deps import TenantContext, own_scope

ZERO = Decimal(0)
INVOICE, CREDIT_NOTE = "invoice", "credit_note"
DRAFT, ISSUED, VOID = "draft", "issued", "void"


class BillingStateError(ConflictError):
    code = "billing_state"
    title = "The document cannot do that in its current state"


class BillingInputError(AppError):
    status = HTTPStatus.UNPROCESSABLE_CONTENT
    code = "billing_input"
    title = "The document details are not valid"


# ---------------------------------------------------------------- helpers


def _round(amount: Decimal, currency: str) -> Decimal:
    return Money(amount, currency).rounded().amount


def _scoped[*Ts](stmt: Select[*Ts], ctx: TenantContext, column: Any) -> Select[*Ts]:
    owner = own_scope(ctx.principal, Perm.CLIENT_READ_ALL)
    return stmt if owner is None else stmt.where(column == owner)


async def get_document(
    ctx: TenantContext, document_id: uuid.UUID, *, kind: str | None = None, lock: bool = False
) -> BillingDocument:
    stmt = _scoped(
        select(BillingDocument).where(BillingDocument.id == document_id),
        ctx,
        BillingDocument.owner_user_id,
    )
    if kind:
        stmt = stmt.where(BillingDocument.kind == kind)
    doc = (await ctx.session.scalars(stmt.with_for_update() if lock else stmt)).first()
    if doc is None:
        raise NotFoundError("Document not found")
    return doc


async def _lines(session: AsyncSession, document_id: uuid.UUID) -> list[BillingLine]:
    stmt = (
        select(BillingLine)
        .where(BillingLine.document_id == document_id)
        .order_by(BillingLine.position)
    )
    return list((await session.scalars(stmt)).all())


async def _live_allocations(
    session: AsyncSession,
    *,
    invoice_ids: list[uuid.UUID] | None = None,
    payment_ids: list[uuid.UUID] | None = None,
    credit_note_ids: list[uuid.UUID] | None = None,
) -> list[Allocation]:
    """Allocations whose source (payment or credit note) is not void."""
    stmt = (
        select(Allocation)
        .outerjoin(Payment, Payment.id == Allocation.payment_id)
        .outerjoin(BillingDocument, BillingDocument.id == Allocation.credit_note_id)
        .where(
            Payment.voided_at.is_(None),
            (BillingDocument.status.is_(None)) | (BillingDocument.status != VOID),
        )
    )
    if invoice_ids is not None:
        stmt = stmt.where(Allocation.invoice_id.in_(invoice_ids))
    if payment_ids is not None:
        stmt = stmt.where(Allocation.payment_id.in_(payment_ids))
    if credit_note_ids is not None:
        stmt = stmt.where(Allocation.credit_note_id.in_(credit_note_ids))
    return list((await session.scalars(stmt.order_by(Allocation.created_at))).all())


async def _paid(session: AsyncSession, docs: list[BillingDocument]) -> dict[uuid.UUID, Decimal]:
    """Invoices: allocated to them. Credit notes: applied from them."""
    invoices = [d.id for d in docs if d.kind == INVOICE]
    notes = [d.id for d in docs if d.kind == CREDIT_NOTE]
    out: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
    for a in await _live_allocations(session, invoice_ids=invoices):
        out[a.invoice_id] += a.amount
    for a in await _live_allocations(session, credit_note_ids=notes):
        out[a.credit_note_id] += a.amount  # type: ignore[index]
    return out


def _status(doc: BillingDocument, paid: Decimal, today: date) -> str:
    if doc.status != ISSUED:
        return doc.status
    if doc.kind == CREDIT_NOTE:
        return ISSUED
    if paid >= doc.total:
        return "paid"
    if doc.due_date is not None and doc.due_date < today:
        return "overdue"
    return "partially_paid" if paid > 0 else "open"


async def _client_ref(session: AsyncSession, client_id: uuid.UUID) -> ClientRef:
    c = (await session.scalars(select(clients.Client).where(clients.Client.id == client_id))).one()
    return ClientRef(id=c.id, display_name=c.display_name, email=c.email, phone=c.phone)


def _summary(doc: BillingDocument, client: ClientRef, paid: Decimal, today: date) -> dict[str, Any]:
    c = doc.currency
    return {
        "id": doc.id,
        "kind": doc.kind,
        "number": doc.number,
        "client": client,
        "status": _status(doc, paid, today),
        "currency": c,
        "issue_date": doc.issue_date,
        "due_date": doc.due_date,
        "total": _round(doc.total, c),
        "paid": _round(paid, c),
        "balance": _round(max(doc.total - paid, ZERO) if doc.status == ISSUED else ZERO, c),
        "created_at": doc.created_at,
    }


async def _allocation_out(
    session: AsyncSession, allocations: list[Allocation], currency: str
) -> list[PaymentAllocationOut]:
    numbers: dict[uuid.UUID, str | None] = {}
    ids = {a.invoice_id for a in allocations} | {
        a.credit_note_id for a in allocations if a.credit_note_id
    }
    if ids:
        for d in await session.scalars(select(BillingDocument).where(BillingDocument.id.in_(ids))):
            numbers[d.id] = d.number
    pay_ids = {a.payment_id for a in allocations if a.payment_id}
    if pay_ids:
        for p in await session.scalars(select(Payment).where(Payment.id.in_(pay_ids))):
            numbers[p.id] = p.number
    out = []
    for a in allocations:
        source_id = a.payment_id or a.credit_note_id
        assert source_id is not None  # noqa: S101 - one source per allocation (DB check)
        out.append(
            PaymentAllocationOut(
                id=a.id,
                invoice_id=a.invoice_id,
                invoice_number=numbers.get(a.invoice_id),
                source="payment" if a.payment_id else "credit_note",
                source_id=source_id,
                source_number=numbers.get(source_id),
                amount=_round(a.amount, currency),
                created_at=a.created_at,
            )
        )
    return out


async def to_out(ctx: TenantContext, doc: BillingDocument) -> BillingDocumentOut:
    today = await tenancy.today(ctx.session, ctx.tenant_id)
    paid = (await _paid(ctx.session, [doc])).get(doc.id, ZERO)
    c = doc.currency
    if doc.kind == INVOICE:
        allocations = await _live_allocations(ctx.session, invoice_ids=[doc.id])
    else:
        allocations = await _live_allocations(ctx.session, credit_note_ids=[doc.id])
    notes = []
    if doc.kind == INVOICE:
        notes = list(
            (
                await ctx.session.scalars(
                    select(BillingDocument.id).where(
                        BillingDocument.credits_document_id == doc.id,
                        BillingDocument.status != VOID,
                    )
                )
            ).all()
        )
    return BillingDocumentOut(
        **_summary(doc, await _client_ref(ctx.session, doc.client_id), paid, today),
        lines=[
            BillingLineOut(
                position=line.position,
                item_id=line.item_id,
                description=line.description,
                quantity=line.quantity.normalize(),
                unit_price=_round(line.unit_price, c),
                discount_rate=format(line.discount_rate.normalize(), "f"),
                tax_code=line.tax_code,
                tax_rate=format(line.tax_rate.normalize(), "f"),
                net=_round(line.net, c),
                tax=_round(line.tax, c),
                total=_round(line.total, c),
            )
            for line in await _lines(ctx.session, doc.id)
        ],
        subtotal=_round(doc.subtotal, c),
        discount=_round(doc.discount, c),
        tax=_round(doc.tax, c),
        taxes=[
            TaxLine(
                code=t["code"],
                name=t["name"],
                rate=t["rate"],
                taxable=_round(Decimal(t["taxable"]), c),
                tax=_round(Decimal(t["tax"]), c),
            )
            for t in doc.taxes
        ],
        prices_include_tax=doc.prices_include_tax,
        payment_reference=doc.payment_reference,
        credits_document_id=doc.credits_document_id,
        reference=doc.reference,
        notes=doc.notes,
        terms=doc.terms,
        issued_at=doc.issued_at,
        voided_at=doc.voided_at,
        void_reason=doc.void_reason,
        allocations=await _allocation_out(ctx.session, allocations, doc.currency),
        credit_notes=notes,
        document_id=doc.document_id,
        version=doc.version,
    )


# ---------------------------------------------------------------- drafts


async def _apply_lines(
    ctx: TenantContext, doc: BillingDocument, lines: list[LineInput], prices_include_tax: bool
) -> None:
    pack, _, _ = await insurers.agency_pack(ctx)
    rows: list[tuple[LineInput, str, Decimal, str]] = []
    for line in lines:
        description, price, code = line.description, line.unit_price, line.tax_code
        if line.item_id is not None:
            item = await catalog.get_item(ctx, line.item_id)
            if item.currency != doc.currency:
                raise BillingInputError(
                    f"{item.name} is priced in {item.currency}, not {doc.currency}"
                )
            description = description or item.name
            price = item.unit_price if price is None else price
            code = code or item.tax_code
        if (
            description is None or price is None or code is None
        ):  # schema-checked; for the type checker
            raise BillingInputError("Each line needs a description, a price and a tax code")
        rows.append((line, description, price, code))
    try:
        totals = calculate_invoice(
            pack,
            [
                LineIn(
                    quantity=line.quantity,
                    unit_price=price,
                    discount_rate=line.discount_rate,
                    tax_code=code,
                )
                for line, _, price, code in rows
            ],
            currency=doc.currency,
            prices_include_tax=prices_include_tax,
        )
    except InvoiceInputError as exc:
        raise BillingInputError(str(exc)) from None
    await ctx.session.execute(delete(BillingLine).where(BillingLine.document_id == doc.id))
    for position, ((line, description, price, _), out) in enumerate(
        zip(rows, totals.lines, strict=True), start=1
    ):
        ctx.session.add(
            BillingLine(
                tenant_id=ctx.tenant_id,
                document_id=doc.id,
                position=position,
                item_id=line.item_id,
                description=description,
                quantity=line.quantity,
                unit_price=price,
                discount_rate=line.discount_rate,
                tax_code=out.tax_code,
                tax_rate=out.tax_rate,
                net=out.net,
                tax=out.tax,
                total=out.total,
            )
        )
    doc.prices_include_tax = prices_include_tax
    doc.subtotal, doc.discount, doc.tax, doc.total = (
        totals.subtotal,
        totals.discount,
        totals.tax,
        totals.total,
    )
    doc.taxes = [t.model_dump(mode="json") for t in totals.taxes]
    doc.pack = {"code": pack.code, "version": pack.version, "signed": pack.signed}


async def create_invoice(ctx: TenantContext, body: InvoiceCreate) -> BillingDocument:
    client = await clients.get_visible_client(ctx, body.client_id)
    tenant = await tenancy.get_tenant(ctx.session, ctx.tenant_id)
    today = await tenancy.today(ctx.session, ctx.tenant_id)
    doc = BillingDocument(
        tenant_id=ctx.tenant_id,
        kind=INVOICE,
        client_id=client.id,
        owner_user_id=client.owner_user_id or ctx.principal.user_id,
        currency=tenant.default_currency,
        due_date=today + timedelta(days=body.due_in_days),
        reference=body.reference,
        notes=body.notes,
        terms=body.terms,
        created_by=ctx.principal.user_id,
        updated_by=ctx.principal.user_id,
    )
    ctx.session.add(doc)
    await ctx.session.flush()
    await _apply_lines(ctx, doc, body.lines, body.prices_include_tax)
    await ctx.session.flush()
    await ctx.session.refresh(doc)
    await audit.record(ctx, "invoice.created", entity_type="invoice", entity_id=doc.id)
    return doc


async def update_draft(
    ctx: TenantContext, document_id: uuid.UUID, body: InvoiceUpdate, if_match: str | None
) -> BillingDocument:
    doc = await get_document(ctx, document_id, lock=True)
    check_version(if_match, doc.version)
    if doc.status != DRAFT:
        raise BillingStateError(
            "Only drafts can be edited; issue a credit note to correct an issued document"
        )
    data = body.model_dump(exclude_unset=True)
    for field in ("reference", "notes", "terms"):
        if field in data:
            setattr(doc, field, data[field])
    if body.due_in_days is not None:
        doc.due_date = await tenancy.today(ctx.session, ctx.tenant_id) + timedelta(
            days=body.due_in_days
        )
    if body.lines is not None or body.prices_include_tax is not None:
        lines = body.lines
        if lines is None:
            lines = [
                LineInput(
                    item_id=line.item_id,
                    description=line.description,
                    quantity=line.quantity,
                    unit_price=line.unit_price,
                    discount_rate=line.discount_rate,
                    tax_code=line.tax_code,
                )
                for line in await _lines(ctx.session, doc.id)
            ]
        include = (
            doc.prices_include_tax if body.prices_include_tax is None else body.prices_include_tax
        )
        await _apply_lines(ctx, doc, lines, include)
    doc.updated_by = ctx.principal.user_id
    await ctx.session.flush()
    await ctx.session.refresh(doc)
    return doc


async def create_credit_note(ctx: TenantContext, body: CreditNoteCreate) -> BillingDocument:
    invoice = await get_document(ctx, body.invoice_id, kind=INVOICE)
    if invoice.status != ISSUED:
        raise BillingStateError("Only issued invoices can be credited")
    doc = BillingDocument(
        tenant_id=ctx.tenant_id,
        kind=CREDIT_NOTE,
        client_id=invoice.client_id,
        owner_user_id=invoice.owner_user_id,
        currency=invoice.currency,
        credits_document_id=invoice.id,
        notes=body.reason,
        created_by=ctx.principal.user_id,
        updated_by=ctx.principal.user_id,
    )
    ctx.session.add(doc)
    await ctx.session.flush()
    lines = body.lines or [
        LineInput(
            item_id=line.item_id,
            description=line.description,
            quantity=line.quantity,
            unit_price=line.unit_price,
            discount_rate=line.discount_rate,
            tax_code=line.tax_code,
        )
        for line in await _lines(ctx.session, invoice.id)
    ]
    await _apply_lines(ctx, doc, lines, invoice.prices_include_tax)
    credited = sum(
        (
            n.total
            for n in (
                await ctx.session.scalars(
                    select(BillingDocument).where(
                        BillingDocument.credits_document_id == invoice.id,
                        BillingDocument.status == ISSUED,
                    )
                )
            ).all()
        ),
        ZERO,
    )
    if credited + doc.total > invoice.total:
        left = _round(max(invoice.total - credited, ZERO), invoice.currency)
        raise BillingInputError(f"Only {left} of {invoice.number} is left to credit")
    await ctx.session.flush()
    await ctx.session.refresh(doc)
    await audit.record(
        ctx,
        "credit_note.created",
        entity_type="credit_note",
        entity_id=doc.id,
        changes={"invoice": invoice.number},
    )
    return doc


# ---------------------------------------------------------------- issue / void


async def _post_allocation(
    ctx: TenantContext, allocation: Allocation, currency: str, client_id: uuid.UUID, on: date
) -> None:
    await ledger.post(
        ctx.session,
        tenant_id=ctx.tenant_id,
        occurred_on=on,
        source_type="allocation",
        source_id=allocation.id,
        memo="Applied to invoice",
        currency=currency,
        client_id=client_id,
        legs=[
            Leg("client_credit", debit=allocation.amount),
            Leg("receivable", credit=allocation.amount),
        ],
        actor=ctx.principal.user_id,
    )


async def _allocate(
    ctx: TenantContext,
    *,
    invoice: BillingDocument,
    amount: Decimal,
    on: date,
    payment: Payment | None = None,
    credit_note: BillingDocument | None = None,
) -> Allocation:
    allocation = Allocation(
        tenant_id=ctx.tenant_id,
        payment_id=payment.id if payment else None,
        credit_note_id=credit_note.id if credit_note else None,
        invoice_id=invoice.id,
        amount=amount,
        created_by=ctx.principal.user_id,
    )
    ctx.session.add(allocation)
    await ctx.session.flush()
    await _post_allocation(ctx, allocation, invoice.currency, invoice.client_id, on)
    return allocation


async def issue(ctx: TenantContext, document_id: uuid.UUID, body: Issue) -> BillingDocument:
    doc = await get_document(ctx, document_id, lock=True)
    if doc.status != DRAFT:
        raise BillingStateError(f"This {doc.kind.replace('_', ' ')} is already {doc.status}")
    on = body.issue_date or await tenancy.today(ctx.session, ctx.tenant_id)
    if doc.kind == INVOICE and doc.due_date is not None and doc.due_date < on:
        doc.due_date = on
    doc.number = (
        await numbering.allocate_number(ctx.session, ctx.tenant_id, doc.kind, on=on)
    ).number
    doc.issue_date, doc.issued_at, doc.issued_by = on, datetime.now(UTC), ctx.principal.user_id
    if doc.kind == INVOICE:
        doc.payment_reference = numbering.generate_payment_reference()
        legs = [
            Leg("receivable", debit=doc.total),
            Leg("revenue", credit=doc.subtotal),
            Leg("tax_payable", credit=doc.tax),
        ]
    else:
        legs = [
            Leg("revenue", debit=doc.subtotal),
            Leg("tax_payable", debit=doc.tax),
            Leg("client_credit", credit=doc.total),
        ]
    doc.status = ISSUED
    await ctx.session.flush()
    await ledger.post(
        ctx.session,
        tenant_id=ctx.tenant_id,
        occurred_on=on,
        source_type=doc.kind,
        source_id=doc.id,
        memo=f"{doc.kind.replace('_', ' ').capitalize()} {doc.number}",
        currency=doc.currency,
        client_id=doc.client_id,
        legs=legs,
        actor=ctx.principal.user_id,
    )
    if doc.kind == CREDIT_NOTE and doc.credits_document_id is not None:
        invoice = await get_document(ctx, doc.credits_document_id, lock=True)
        balance = invoice.total - (await _paid(ctx.session, [invoice])).get(invoice.id, ZERO)
        if balance > 0:
            await _allocate(
                ctx, invoice=invoice, amount=min(balance, doc.total), on=on, credit_note=doc
            )
    await audit.record(
        ctx,
        f"{doc.kind}.issued",
        entity_type=doc.kind,
        entity_id=doc.id,
        changes={"number": doc.number, "total": str(doc.total)},
    )
    await ctx.session.flush()
    await ctx.session.refresh(doc)
    return doc


async def void(ctx: TenantContext, document_id: uuid.UUID, body: Void) -> BillingDocument:
    doc = await get_document(ctx, document_id, lock=True)
    if doc.status == VOID:
        raise BillingStateError("Already void")
    on = await tenancy.today(ctx.session, ctx.tenant_id)
    if doc.status == ISSUED:
        if doc.kind == INVOICE:
            if await _live_allocations(ctx.session, invoice_ids=[doc.id]):
                raise BillingStateError(
                    "Payments or credits are applied to this invoice: issue a credit note instead"
                )
        else:
            for allocation in await _live_allocations(ctx.session, credit_note_ids=[doc.id]):
                await ledger.reverse(
                    ctx.session,
                    tenant_id=ctx.tenant_id,
                    source_type="allocation",
                    source_id=allocation.id,
                    occurred_on=on,
                    memo=f"Void {doc.number}",
                    actor=ctx.principal.user_id,
                )
        await ledger.reverse(
            ctx.session,
            tenant_id=ctx.tenant_id,
            source_type=doc.kind,
            source_id=doc.id,
            occurred_on=on,
            memo=f"Void {doc.number}",
            actor=ctx.principal.user_id,
        )
    doc.status, doc.voided_at, doc.void_reason = VOID, datetime.now(UTC), body.reason
    doc.updated_by = ctx.principal.user_id
    await links.revoke_for_entity(ctx, doc.kind, doc.id)
    await audit.record(
        ctx,
        f"{doc.kind}.voided",
        entity_type=doc.kind,
        entity_id=doc.id,
        changes={"reason": body.reason},
    )
    await ctx.session.flush()
    await ctx.session.refresh(doc)
    return doc


# ---------------------------------------------------------------- lists


async def list_documents(
    ctx: TenantContext, *, kind: str, client_id: uuid.UUID | None, status: str | None, limit: int
) -> list[BillingDocumentSummary]:
    today = await tenancy.today(ctx.session, ctx.tenant_id)
    stmt = _scoped(
        select(BillingDocument).where(BillingDocument.kind == kind),
        ctx,
        BillingDocument.owner_user_id,
    )
    if client_id is not None:
        stmt = stmt.where(BillingDocument.client_id == client_id)
    if status in {DRAFT, VOID}:
        stmt = stmt.where(BillingDocument.status == status)
    elif status:
        stmt = stmt.where(BillingDocument.status == ISSUED)
    docs = list(
        (await ctx.session.scalars(stmt.order_by(BillingDocument.id.desc()).limit(limit))).all()
    )
    paid = await _paid(ctx.session, docs)
    refs: dict[uuid.UUID, ClientRef] = {}
    out = []
    for d in docs:
        if d.client_id not in refs:
            refs[d.client_id] = await _client_ref(ctx.session, d.client_id)
        out.append(
            BillingDocumentSummary(**_summary(d, refs[d.client_id], paid.get(d.id, ZERO), today))
        )
    if status and status not in {DRAFT, VOID}:
        wanted = {"unpaid": {"open", "partially_paid", "overdue"}}.get(status, {status})
        out = [d for d in out if d.status in wanted]
    return out


# ---------------------------------------------------------------- payments


async def get_payment(ctx: TenantContext, payment_id: uuid.UUID, *, lock: bool = False) -> Payment:
    stmt = select(Payment).where(Payment.id == payment_id)
    payment = (await ctx.session.scalars(stmt.with_for_update() if lock else stmt)).first()
    if payment is None:
        raise NotFoundError("Payment not found")
    await clients.get_visible_client(
        ctx, payment.client_id
    )  # agents see their own clients' payments
    return payment


async def payment_out(ctx: TenantContext, payment: Payment) -> ReceivedPayment:
    allocations = (
        [] if payment.voided_at else await _live_allocations(ctx.session, payment_ids=[payment.id])
    )
    applied = sum((a.amount for a in allocations), ZERO)
    c = payment.currency
    return ReceivedPayment(
        id=payment.id,
        number=payment.number,
        client=await _client_ref(ctx.session, payment.client_id),
        received_on=payment.received_on,
        amount=_round(payment.amount, c),
        currency=c,
        method=payment.method,
        reference=payment.reference,
        notes=payment.notes,
        unallocated=_round(ZERO if payment.voided_at else payment.amount - applied, c),
        allocations=await _allocation_out(ctx.session, allocations, payment.currency),
        voided_at=payment.voided_at,
        void_reason=payment.void_reason,
        created_at=payment.created_at,
    )


async def _open_invoices(
    ctx: TenantContext, client_id: uuid.UUID, currency: str
) -> list[tuple[BillingDocument, Decimal]]:
    """The client's issued invoices with a balance, oldest first (locked for allocation)."""
    stmt = (
        select(BillingDocument)
        .where(
            BillingDocument.client_id == client_id,
            BillingDocument.kind == INVOICE,
            BillingDocument.status == ISSUED,
            BillingDocument.currency == currency,
        )
        .order_by(BillingDocument.issue_date, BillingDocument.number)
        .with_for_update()
    )
    docs = list((await ctx.session.scalars(stmt)).all())
    paid = await _paid(ctx.session, docs)
    return [(d, d.total - paid.get(d.id, ZERO)) for d in docs if d.total - paid.get(d.id, ZERO) > 0]


async def _apply(
    ctx: TenantContext,
    *,
    client_id: uuid.UUID,
    currency: str,
    amount: Decimal,
    on: date,
    explicit: list[PaymentAllocationIn] | None,
    payment: Payment | None = None,
    credit_note: BillingDocument | None = None,
) -> Decimal:
    """Apply up to ``amount`` to open invoices; returns what was applied."""
    open_ = await _open_invoices(ctx, client_id, currency)
    balances = {d.id: (d, b) for d, b in open_}
    plan: list[tuple[BillingDocument, Decimal]] = []
    if explicit is not None:
        for item in explicit:
            if item.invoice_id not in balances:
                raise BillingInputError(
                    "Payments can only be applied to this client's unpaid invoices"
                )
            doc, balance = balances[item.invoice_id]
            if item.amount > balance:
                raise BillingInputError(
                    f"{doc.number} has only {_round(balance, currency)} left to pay"
                )
            plan.append((doc, item.amount))
        if sum((a for _, a in plan), ZERO) > amount:
            raise BillingInputError("The allocations add up to more than the payment")
    else:
        left = amount
        for doc, balance in open_:
            if left <= 0:
                break
            part = min(left, balance)
            plan.append((doc, part))
            left -= part
    for doc, part in plan:
        await _allocate(
            ctx, invoice=doc, amount=part, on=on, payment=payment, credit_note=credit_note
        )
    return sum((a for _, a in plan), ZERO)


async def record_payment(ctx: TenantContext, body: PaymentCreate) -> Payment:
    client = await clients.get_visible_client(ctx, body.client_id)
    tenant = await tenancy.get_tenant(ctx.session, ctx.tenant_id)
    currency = tenant.default_currency
    payment = Payment(
        tenant_id=ctx.tenant_id,
        number=(
            await numbering.allocate_number(
                ctx.session, ctx.tenant_id, "receipt", on=body.received_on
            )
        ).number,
        client_id=client.id,
        received_on=body.received_on,
        amount=body.amount,
        currency=currency,
        method=body.method,
        reference=body.reference,
        notes=body.notes,
        created_by=ctx.principal.user_id,
    )
    ctx.session.add(payment)
    await ctx.session.flush()
    await ledger.post(
        ctx.session,
        tenant_id=ctx.tenant_id,
        occurred_on=body.received_on,
        source_type="payment",
        source_id=payment.id,
        memo=f"Payment {payment.number}",
        currency=currency,
        client_id=client.id,
        legs=[Leg("cash", debit=body.amount), Leg("client_credit", credit=body.amount)],
        actor=ctx.principal.user_id,
    )
    await _apply(
        ctx,
        client_id=client.id,
        currency=currency,
        amount=body.amount,
        on=body.received_on,
        explicit=body.allocations,
        payment=payment,
    )
    await audit.record(
        ctx,
        "payment.recorded",
        entity_type="payment",
        entity_id=payment.id,
        changes={
            "amount": str(body.amount),
            "method": body.method,
            "reference": body.reference or "",
        },
    )
    await ctx.session.flush()
    await ctx.session.refresh(payment)
    return payment


async def void_payment(ctx: TenantContext, payment_id: uuid.UUID, body: Void) -> Payment:
    payment = await get_payment(ctx, payment_id, lock=True)
    if payment.voided_at is not None:
        raise BillingStateError("The payment was already voided")
    on = await tenancy.today(ctx.session, ctx.tenant_id)
    for allocation in await _live_allocations(ctx.session, payment_ids=[payment.id]):
        await ledger.reverse(
            ctx.session,
            tenant_id=ctx.tenant_id,
            source_type="allocation",
            source_id=allocation.id,
            occurred_on=on,
            memo=f"Void {payment.number}",
            actor=ctx.principal.user_id,
        )
    await ledger.reverse(
        ctx.session,
        tenant_id=ctx.tenant_id,
        source_type="payment",
        source_id=payment.id,
        occurred_on=on,
        memo=f"Void {payment.number}",
        actor=ctx.principal.user_id,
    )
    payment.voided_at, payment.void_reason, payment.voided_by = (
        datetime.now(UTC),
        body.reason,
        ctx.principal.user_id,
    )
    await audit.record(
        ctx,
        "payment.voided",
        entity_type="payment",
        entity_id=payment.id,
        changes={"reason": body.reason},
    )
    await ctx.session.flush()
    await ctx.session.refresh(payment)
    return payment


async def _credit_sources(
    ctx: TenantContext, client_id: uuid.UUID, currency: str
) -> list[tuple[Payment | BillingDocument, Decimal]]:
    payments = list(
        (
            await ctx.session.scalars(
                select(Payment)
                .where(
                    Payment.client_id == client_id,
                    Payment.currency == currency,
                    Payment.voided_at.is_(None),
                )
                .order_by(Payment.received_on, Payment.number)
                .with_for_update()
            )
        ).all()
    )
    notes = list(
        (
            await ctx.session.scalars(
                select(BillingDocument)
                .where(
                    BillingDocument.client_id == client_id,
                    BillingDocument.kind == CREDIT_NOTE,
                    BillingDocument.status == ISSUED,
                    BillingDocument.currency == currency,
                )
                .order_by(BillingDocument.issue_date)
                .with_for_update()
            )
        ).all()
    )
    used: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
    for a in await _live_allocations(ctx.session, payment_ids=[p.id for p in payments]):
        used[a.payment_id] += a.amount  # type: ignore[index]
    for a in await _live_allocations(ctx.session, credit_note_ids=[n.id for n in notes]):
        used[a.credit_note_id] += a.amount  # type: ignore[index]
    out: list[tuple[Payment | BillingDocument, Decimal]] = [
        (p, p.amount - used[p.id]) for p in payments if p.amount - used[p.id] > 0
    ]
    out.extend((n, n.total - used[n.id]) for n in notes if n.total - used[n.id] > 0)
    return out


async def apply_credit(ctx: TenantContext, invoice_id: uuid.UUID) -> BillingDocument:
    """Apply the client's unused payments and credit notes to this invoice (oldest first)."""
    invoice = await get_document(ctx, invoice_id, kind=INVOICE, lock=True)
    if invoice.status != ISSUED:
        raise BillingStateError("Only issued invoices can be paid")
    balance = invoice.total - (await _paid(ctx.session, [invoice])).get(invoice.id, ZERO)
    on = await tenancy.today(ctx.session, ctx.tenant_id)
    for source, available in await _credit_sources(ctx, invoice.client_id, invoice.currency):
        if balance <= 0:
            break
        part = min(balance, available)
        if isinstance(source, Payment):
            await _allocate(ctx, invoice=invoice, amount=part, on=on, payment=source)
        else:
            await _allocate(ctx, invoice=invoice, amount=part, on=on, credit_note=source)
        balance -= part
    await ctx.session.flush()
    await ctx.session.refresh(invoice)
    return invoice


async def client_account(ctx: TenantContext, client_id: uuid.UUID) -> ClientAccount:
    client = await clients.get_visible_client(ctx, client_id)
    tenant = await tenancy.get_tenant(ctx.session, ctx.tenant_id)
    currency = tenant.default_currency
    owed = await ledger.balance(ctx.session, "receivable", client_id=client.id, currency=currency)
    credit = -await ledger.balance(
        ctx.session, "client_credit", client_id=client.id, currency=currency
    )
    return ClientAccount(
        client=await _client_ref(ctx.session, client.id),
        currency=currency,
        owed=_round(owed, currency),
        credit=_round(credit, currency),
        open_invoices=await list_documents(
            ctx, kind=INVOICE, client_id=client.id, status="unpaid", limit=200
        ),
    )


# ---------------------------------------------------------------- documents, sending, public page


async def _seller(session: AsyncSession, tenant_id: uuid.UUID) -> Party:
    t = await tenancy.get_tenant(session, tenant_id)
    lines = [v for v in (t.address or {}).values() if isinstance(v, str) and v]
    return Party(
        name=t.legal_name or t.name,
        address_lines=lines,
        tax_pin=t.tax_pin,
        email=t.email,
        phone=t.phone,
    )


async def document_view(
    session: AsyncSession, tenant_id: uuid.UUID, doc: BillingDocument
) -> DocumentView:
    client = (
        await session.scalars(select(clients.Client).where(clients.Client.id == doc.client_id))
    ).one()
    lines = await _lines(session, doc.id)
    paid = (await _paid(session, [doc])).get(doc.id, ZERO) if doc.kind == INVOICE else ZERO
    charges = [
        AmountLine(label=f"{t['name']}", amount=Decimal(t["tax"]))
        for t in doc.taxes
        if Decimal(t["tax"]) != 0
    ]
    details = []
    if doc.reference:
        details.append(KeyValue(label="Your reference", value=doc.reference))
    if doc.kind == CREDIT_NOTE and doc.credits_document_id:
        original = await session.get(BillingDocument, doc.credits_document_id)
        if original is not None:
            details.append(KeyValue(label="Credits invoice", value=original.number or ""))
    stamp: Literal["DRAFT", "PAID", "VOID"] | None = None
    if doc.status == DRAFT:
        stamp = "DRAFT"
    elif doc.status == VOID:
        stamp = "VOID"
    elif doc.kind == INVOICE and paid >= doc.total:
        stamp = "PAID"
    return DocumentView(
        doc_type="invoice" if doc.kind == INVOICE else "credit_note",
        number=doc.number,
        issue_date=doc.issue_date or datetime.now(UTC).date(),
        due_date=doc.due_date if doc.kind == INVOICE else None,
        reference=doc.reference,
        currency=doc.currency,
        seller=await _seller(session, tenant_id),
        buyer=Party(
            name=client.display_name, email=client.email, phone=client.phone, tax_pin=client.kra_pin
        ),
        details=details,
        lines=[
            LineItem(
                description=line.description,
                details=f"{line.discount_rate * 100:g}% discount" if line.discount_rate else None,
                quantity=line.quantity.normalize(),
                unit_price=line.unit_price,
                amount=line.net,
            )
            for line in lines
        ],
        totals=Totals(
            subtotal=doc.subtotal,
            charges=charges,
            total=doc.total,
            amount_paid=paid if doc.kind == INVOICE and paid else None,
            balance=max(doc.total - paid, ZERO) if doc.kind == INVOICE and paid else None,
        ),
        notes=doc.notes,
        terms=doc.terms,
        payment=PaymentInstructions(reference=doc.payment_reference)
        if doc.payment_reference
        else None,
        stamp=stamp,
    )


async def _pdf(
    ctx: TenantContext, doc: BillingDocument, storage: S3Storage, renderer: PdfRenderer
) -> uuid.UUID:
    pdf = await rendering.generate_pdf(
        ctx.session,
        storage,
        renderer,
        tenant_id=ctx.tenant_id,
        view=await document_view(ctx.session, ctx.tenant_id, doc),
        entity=documents.EntityRef(entity_type=doc.kind, entity_id=doc.id),
        actor=ctx.principal.user_id,
    )
    return pdf.id


async def pdf_url(
    ctx: TenantContext,
    document_id: uuid.UUID,
    *,
    settings: Settings,
    storage: S3Storage,
    renderer: PdfRenderer,
) -> str:
    doc = await get_document(ctx, document_id)
    document_id_ = await _pdf(ctx, doc, storage, renderer)
    if doc.status != DRAFT and doc.document_id != document_id_:
        doc.document_id = document_id_
        await ctx.session.flush()
    return (
        await documents.download_url(ctx.session, document_id_, storage, settings, inline=True)
    ).url


async def send(
    ctx: TenantContext,
    document_id: uuid.UUID,
    body: Send,
    *,
    settings: Settings,
    storage: S3Storage,
    renderer: PdfRenderer,
) -> tuple[BillingDocument, str, str | None, str | None]:
    doc = await get_document(ctx, document_id, lock=True)
    if doc.status != ISSUED:
        raise BillingStateError("Issue the document before sending it")
    doc.document_id = await _pdf(ctx, doc, storage, renderer)
    client = await clients.get_visible_client(ctx, doc.client_id)
    email = str(body.email) if body.email else client.email
    _, token = await links.create_link(
        ctx,
        links.LinkCreate(
            entity_type=doc.kind,
            entity_id=doc.id,
            scopes=["view"],
            expires_in_days=180,
            send_to=links.SendTo(email=email, name=client.display_name, message=body.message)
            if email
            else None,
        ),
        settings,
        storage,
    )
    url = links.link_url(token, settings)
    whatsapp = None
    if client.phone:
        label = "invoice" if doc.kind == INVOICE else "credit note"
        text = f"Hello {client.display_name}, here is your {label} {doc.number}: {url}"
        whatsapp = f"https://wa.me/{client.phone.lstrip('+')}?text={urlquote(text)}"
    await audit.record(
        ctx,
        f"{doc.kind}.sent",
        entity_type=doc.kind,
        entity_id=doc.id,
        changes={"emailed_to": email or ""},
    )
    await ctx.session.flush()
    await ctx.session.refresh(doc)
    return doc, url, email, whatsapp


def _target_for(kind: str) -> links.TargetResolver:
    async def target(
        session: AsyncSession, storage: S3Storage, settings: Settings, link: links.PublicLink
    ) -> links.PublicContent:
        doc = (
            await session.scalars(
                select(BillingDocument).where(BillingDocument.id == link.entity_id)
            )
        ).first()
        if doc is None or doc.kind != kind or doc.status == DRAFT:
            raise links.LinkGoneError()
        paid = (await _paid(session, [doc])).get(doc.id, ZERO)
        today = await tenancy.today(session, link.tenant_id)

        async def html() -> str:
            view = await document_view(session, link.tenant_id, doc)
            return await rendering.render_html_for(session, storage, link.tenant_id, view)

        async def download() -> str:
            if doc.document_id is None:
                raise links.LinkGoneError()
            return (
                await documents.download_url(
                    session, doc.document_id, storage, settings, inline=True
                )
            ).url

        label = "Invoice" if kind == INVOICE else "Credit note"
        return links.PublicContent(
            title=f"{label} {doc.number}",
            kind=kind,
            html=html,
            download=download if doc.document_id else None,
            state=_status(doc, paid, today),
        )

    return target


links.register_target(INVOICE, _target_for(INVOICE))
links.register_target(CREDIT_NOTE, _target_for(CREDIT_NOTE))


async def receipt_url(
    ctx: TenantContext,
    payment_id: uuid.UUID,
    *,
    settings: Settings,
    storage: S3Storage,
    renderer: PdfRenderer,
) -> str:
    """The numbered receipt for a payment: what it paid, and any credit left on account."""
    payment = await get_payment(ctx, payment_id)
    out = await payment_out(ctx, payment)
    client = (
        await ctx.session.scalars(
            select(clients.Client).where(clients.Client.id == payment.client_id)
        )
    ).one()
    lines = [
        LineItem(
            description=f"Payment towards invoice {a.invoice_number}",
            unit_price=a.amount,
            amount=a.amount,
        )
        for a in out.allocations
    ]
    if out.unallocated > 0:
        lines.append(
            LineItem(
                description="Credit on account", unit_price=out.unallocated, amount=out.unallocated
            )
        )
    method = {
        "mpesa": "M-Pesa",
        "bank": "Bank transfer",
        "card": "Card",
        "cheque": "Cheque",
        "cash": "Cash",
    }.get(payment.method, "Other")
    view = DocumentView(
        doc_type="receipt",
        number=payment.number,
        issue_date=payment.received_on,
        currency=payment.currency,
        seller=await _seller(ctx.session, ctx.tenant_id),
        buyer=Party(
            name=client.display_name, email=client.email, phone=client.phone, tax_pin=client.kra_pin
        ),
        details=[
            KeyValue(
                label="Paid by",
                value=method + (f" ({payment.reference})" if payment.reference else ""),
            )
        ],
        lines=lines,
        totals=Totals(subtotal=payment.amount, total=payment.amount),
        notes=payment.notes,
        stamp="VOID" if payment.voided_at else None,
    )
    pdf = await rendering.generate_pdf(
        ctx.session,
        storage,
        renderer,
        tenant_id=ctx.tenant_id,
        view=view,
        entity=documents.EntityRef(entity_type="payment", entity_id=payment.id),
        actor=ctx.principal.user_id,
    )
    if payment.document_id != pdf.id and payment.voided_at is None:
        payment.document_id = pdf.id
        await ctx.session.flush()
    return (await documents.download_url(ctx.session, pdf.id, storage, settings, inline=True)).url


async def list_payments(
    ctx: TenantContext, *, client_id: uuid.UUID | None, limit: int
) -> list[ReceivedPayment]:
    stmt = select(Payment).join(clients.Client, clients.Client.id == Payment.client_id)
    owner = own_scope(ctx.principal, Perm.CLIENT_READ_ALL)
    if owner is not None:
        stmt = stmt.where(clients.Client.owner_user_id == owner)
    if client_id is not None:
        stmt = stmt.where(Payment.client_id == client_id)
    rows = (
        await ctx.session.scalars(
            stmt.order_by(Payment.received_on.desc(), Payment.number.desc()).limit(limit)
        )
    ).all()
    return [await payment_out(ctx, p) for p in rows]
