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
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from http import HTTPStatus
from typing import Any, Literal
from urllib.parse import quote as urlquote
from urllib.parse import urlsplit

from sqlalchemy import Select, delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.calc.invoice import InvoiceInputError, LineIn, calculate_invoice
from app.core.concurrency import check_version
from app.core.config import Settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.money import Money
from app.core.permissions import Perm
from app.integrations.pdf import PdfRenderer
from app.integrations.storage.s3 import S3Storage
from app.modules.billing.models import (
    Allocation,
    BillingDocument,
    BillingLine,
    BillingReminder,
    Payment,
)

__all__ = [
    "BillingDocument",
    "Payable",
    "PaymentAllocationIn",
    "PaymentCreate",
    "find_by_payment_reference",
    "payable",
    "record_payment",
]
from app.modules.billing.schemas import (
    AgeingBucket,
    BillingDocumentOut,
    BillingDocumentSummary,
    BillingLineOut,
    BillingSummary,
    ClientAccount,
    CreditNoteCreate,
    EtimsIn,
    InvoiceCreate,
    InvoiceUpdate,
    Issue,
    LineInput,
    MonthBilling,
    PaymentAllocationIn,
    PaymentAllocationOut,
    PaymentCreate,
    QuoteAccept,
    QuoteDecline,
    ReceivedPayment,
    SalesQuoteCreate,
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
from app.modules.messaging import service as messaging
from app.modules.notifications import service as notifications
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
from app.platform import audit, events
from app.platform.deps import TenantContext, own_scope

ZERO = Decimal(0)
INVOICE, CREDIT_NOTE, QUOTE = "invoice", "credit_note", "quote"
# Public links: insurance quotes already own the "quote" entity type.
# Invoices can be paid from their link (when the tenant has M-Pesa connected); quotes accepted.
_LINK_SCOPES: dict[str, list[Literal["view", "accept", "pay"]]] = {
    "invoice": ["view", "pay"],
    "credit_note": ["view"],
    "quote": ["view", "accept"],
}
LINK_ENTITY = {INVOICE: "invoice", CREDIT_NOTE: "credit_note", QUOTE: "sales_quote"}
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


def _quote_status(doc: BillingDocument, today: date) -> str:
    if doc.converted_document_id is not None:
        return "invoiced"
    if doc.response_status is not None:
        return doc.response_status
    return "expired" if doc.valid_until is not None and doc.valid_until < today else "sent"


def _invoice_status(doc: BillingDocument, paid: Decimal, today: date) -> str:
    if paid >= doc.total:
        return "paid"
    if doc.due_date is not None and doc.due_date < today:
        return "overdue"
    return "partially_paid" if paid > 0 else "open"


def _status(doc: BillingDocument, paid: Decimal, today: date) -> str:
    """Derived status (ADR-0009): never stored."""
    if doc.status != ISSUED:
        return doc.status
    if doc.kind == QUOTE:
        return _quote_status(doc, today)
    return _invoice_status(doc, paid, today) if doc.kind == INVOICE else ISSUED


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
        "valid_until": doc.valid_until,
        "total": _round(doc.total, c),
        "paid": _round(paid, c),
        "etims_cu_invoice_number": doc.etims_cu_invoice_number,
        "balance": _round(
            max(doc.total - paid, ZERO) if doc.status == ISSUED and doc.kind != QUOTE else ZERO, c
        ),
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
    lines = await _lines(ctx.session, doc.id)
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
                section=line.section,
                optional=line.optional,
                tax_rate=format(line.tax_rate.normalize(), "f"),
                net=_round(line.net, c),
                tax=_round(line.tax, c),
                total=_round(line.total, c),
            )
            for line in lines
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
        optional_total=_round(sum((line.total for line in lines if line.optional), ZERO), c),
        response_status=doc.response_status,
        responded_at=doc.responded_at,
        response=doc.response,
        converted_document_id=doc.converted_document_id,
        etims_verification_url=doc.etims_verification_url,
        etims_recorded_at=doc.etims_recorded_at,
        issued_at=doc.issued_at,
        voided_at=doc.voided_at,
        void_reason=doc.void_reason,
        allocations=await _allocation_out(ctx.session, allocations, doc.currency),
        credit_notes=notes,
        document_id=doc.document_id,
        version=doc.version,
    )


# ---------------------------------------------------------------- drafts


def _as_input(line: BillingLine, *, optional: bool | None = None) -> LineInput:
    """A stored line as input again (editing a draft, crediting an invoice, invoicing a quote)."""
    return LineInput(
        item_id=line.item_id,
        description=line.description,
        quantity=line.quantity,
        unit_price=line.unit_price,
        discount_rate=line.discount_rate,
        tax_code=line.tax_code,
        section=line.section,
        optional=line.optional if optional is None else optional,
    )


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
    if doc.kind != QUOTE and any(line.optional for line, *_ in rows):
        raise BillingInputError("Only quotes can have optional lines")
    if all(line.optional for line, *_ in rows):
        raise BillingInputError("At least one line must be part of the total")

    def calc_lines(selected: list[tuple[LineInput, str, Decimal, str]]) -> list[LineIn]:
        return [
            LineIn(
                quantity=line.quantity,
                unit_price=price,
                discount_rate=line.discount_rate,
                tax_code=code,
            )
            for line, _, price, code in selected
        ]

    try:
        # Per line (rounded per line), then the document totals over the lines that count.
        every = calculate_invoice(
            pack, calc_lines(rows), currency=doc.currency, prices_include_tax=prices_include_tax
        )
        totals = calculate_invoice(
            pack,
            calc_lines([r for r in rows if not r[0].optional]),
            currency=doc.currency,
            prices_include_tax=prices_include_tax,
        )
    except InvoiceInputError as exc:
        raise BillingInputError(str(exc)) from None
    await ctx.session.execute(delete(BillingLine).where(BillingLine.document_id == doc.id))
    for position, ((line, description, price, _), out) in enumerate(
        zip(rows, every.lines, strict=True), start=1
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
                section=line.section,
                optional=line.optional,
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


async def create_sales_quote(ctx: TenantContext, body: SalesQuoteCreate) -> BillingDocument:
    client = await clients.get_visible_client(ctx, body.client_id)
    tenant = await tenancy.get_tenant(ctx.session, ctx.tenant_id)
    today = await tenancy.today(ctx.session, ctx.tenant_id)
    doc = BillingDocument(
        tenant_id=ctx.tenant_id,
        kind=QUOTE,
        client_id=client.id,
        owner_user_id=client.owner_user_id or ctx.principal.user_id,
        currency=tenant.default_currency,
        valid_until=today + timedelta(days=body.valid_days),
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
    await audit.record(ctx, "sales_quote.created", entity_type="quote", entity_id=doc.id)
    return doc


async def convert_quote(ctx: TenantContext, quote_id: uuid.UUID) -> BillingDocument:
    """A draft invoice from a quote: its lines, plus the extras the client chose (as ordinary lines)."""
    quote = await get_document(ctx, quote_id, kind=QUOTE, lock=True)
    state = _status(quote, ZERO, await tenancy.today(ctx.session, ctx.tenant_id))
    if state not in {"sent", "accepted", "expired"}:
        raise BillingStateError(f"A {state} quote cannot be invoiced")
    chosen = set(quote.response.get("addons", [])) if quote.response_status == "accepted" else set()
    lines = [
        _as_input(line, optional=False)
        for line in await _lines(ctx.session, quote.id)
        if not line.optional or line.position in chosen
    ]
    today = await tenancy.today(ctx.session, ctx.tenant_id)
    invoice = BillingDocument(
        tenant_id=ctx.tenant_id,
        kind=INVOICE,
        client_id=quote.client_id,
        owner_user_id=quote.owner_user_id,
        currency=quote.currency,
        due_date=today + timedelta(days=14),
        reference=quote.reference or quote.number,
        notes=quote.notes,
        terms=quote.terms,
        created_by=ctx.principal.user_id,
        updated_by=ctx.principal.user_id,
    )
    ctx.session.add(invoice)
    await ctx.session.flush()
    await _apply_lines(ctx, invoice, lines, quote.prices_include_tax)
    quote.converted_document_id = invoice.id
    quote.updated_by = ctx.principal.user_id
    await audit.record(
        ctx,
        "sales_quote.invoiced",
        entity_type="quote",
        entity_id=quote.id,
        changes={"invoice_id": str(invoice.id)},
    )
    await ctx.session.flush()
    await ctx.session.refresh(invoice)
    return invoice


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
    if body.valid_days is not None and doc.kind == QUOTE:
        doc.valid_until = await tenancy.today(ctx.session, ctx.tenant_id) + timedelta(
            days=body.valid_days
        )
    if body.due_in_days is not None and doc.kind == INVOICE:
        doc.due_date = await tenancy.today(ctx.session, ctx.tenant_id) + timedelta(
            days=body.due_in_days
        )
    if body.lines is not None or body.prices_include_tax is not None:
        lines = body.lines
        if lines is None:
            lines = [_as_input(line) for line in await _lines(ctx.session, doc.id)]
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
    lines = body.lines or [_as_input(line) for line in await _lines(ctx.session, invoice.id)]
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
    if doc.kind == QUOTE and (doc.valid_until is None or doc.valid_until < on):
        raise BillingInputError(
            "The quote's validity has passed: set how many days it is valid for"
        )
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
    elif doc.kind == CREDIT_NOTE:
        legs = [
            Leg("revenue", debit=doc.subtotal),
            Leg("tax_payable", debit=doc.tax),
            Leg("client_credit", credit=doc.total),
        ]
    else:
        legs = []  # a quote is an offer: nothing to book until it becomes an invoice
    doc.status = ISSUED
    await ctx.session.flush()
    if legs:
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
    if doc.kind == QUOTE and doc.converted_document_id is not None:
        raise BillingStateError("This quote became an invoice: void or credit the invoice instead")
    await links.revoke_for_entity(ctx, LINK_ENTITY[doc.kind], doc.id)
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
        wanted = {
            "unpaid": {"open", "partially_paid", "overdue"},
            "awaiting": {"sent"},
        }.get(status, {status})
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
        doc_type={INVOICE: "invoice", CREDIT_NOTE: "credit_note", QUOTE: "quote"}[doc.kind],  # type: ignore[arg-type]
        number=doc.number,
        issue_date=doc.issue_date or datetime.now(UTC).date(),
        due_date=doc.due_date if doc.kind == INVOICE else None,
        valid_until=doc.valid_until if doc.kind == QUOTE else None,
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
                section=line.section,
                optional=line.optional,
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
        tax_control=[
            KeyValue(label="KRA CU invoice no.", value=doc.etims_cu_invoice_number),
            *(
                [KeyValue(label="Verify on KRA eTIMS", value=doc.etims_verification_url)]
                if doc.etims_verification_url
                else []
            ),
        ]
        if doc.etims_cu_invoice_number
        else [],
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
    if doc.kind == QUOTE and doc.status == DRAFT:
        doc = await issue(ctx, document_id, Issue())  # sending a quote is what issues it
    if doc.status != ISSUED:
        raise BillingStateError("Issue the document before sending it")
    if (
        doc.kind == QUOTE
        and _status(doc, ZERO, await tenancy.today(ctx.session, ctx.tenant_id)) != "sent"
    ):
        raise BillingStateError("Only a quote awaiting an answer can be sent")
    doc.document_id = await _pdf(ctx, doc, storage, renderer)
    client = await clients.get_visible_client(ctx, doc.client_id)
    email = str(body.email) if body.email else client.email
    _, token = await links.create_link(
        ctx,
        links.LinkCreate(
            entity_type=LINK_ENTITY[doc.kind],
            entity_id=doc.id,
            scopes=_LINK_SCOPES[doc.kind],
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
        label = {INVOICE: "invoice", CREDIT_NOTE: "credit note", QUOTE: "quotation"}[doc.kind]
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

        label = {INVOICE: "Invoice", CREDIT_NOTE: "Credit note", QUOTE: "Quotation"}[kind]
        choices: list[dict[str, Any]] = []
        if kind == QUOTE:
            choices = [
                {
                    "position": line.position,
                    "label": line.description,
                    "amount": str(_round(line.total, doc.currency)),
                    "currency": doc.currency,
                    "kind": "addon",
                }
                for line in await _lines(session, doc.id)
                if line.optional
            ]
        return links.PublicContent(
            title=f"{label} {doc.number}",
            kind=LINK_ENTITY[kind],
            html=html,
            download=download if doc.document_id else None,
            state=_status(doc, paid, today),
            choices=choices,
        )

    return target


links.register_target(INVOICE, _target_for(INVOICE))
links.register_target(CREDIT_NOTE, _target_for(CREDIT_NOTE))
links.register_target(LINK_ENTITY[QUOTE], _target_for(QUOTE))


async def _quote_action(
    *,
    session: AsyncSession,
    settings: Settings,
    link: links.PublicLink,
    action: str,
    body: dict[str, Any],
    evidence: dict[str, Any],
) -> str:
    """The client accepts (with any add-ons) or declines a sales quote on the link."""
    doc = (
        await session.scalars(
            select(BillingDocument).where(BillingDocument.id == link.entity_id).with_for_update()
        )
    ).first()
    if doc is None or doc.kind != QUOTE:
        raise links.LinkGoneError()
    state = _status(doc, ZERO, await tenancy.today(session, link.tenant_id))
    if state != "sent":
        raise BillingStateError(f"This quotation is {state} and can no longer be answered")
    if action == "accept":
        accepted = QuoteAccept.model_validate(body)
        optional = {line.position for line in await _lines(session, doc.id) if line.optional}
        if not set(accepted.addons) <= optional:
            raise NotFoundError("That extra is not on this quotation")
        doc.response_status = "accepted"
        doc.response = {
            "action": "accept",
            "name": accepted.name,
            "phone": accepted.phone,
            "email": str(accepted.email) if accepted.email else None,
            "addons": sorted(accepted.addons),
            "agreed_terms": True,
            **evidence,
        }
        title = f"{accepted.name} accepted quotation {doc.number}"
    else:
        declined = QuoteDecline.model_validate(body)
        doc.response_status = "declined"
        doc.response = {"action": "decline", "reason": declined.reason, **evidence}
        title = f"Quotation {doc.number} was declined"
    doc.responded_at = datetime.now(UTC)
    await audit.record_actor(
        session,
        link.tenant_id,
        f"sales_quote.{doc.response_status}",
        actor_type="client",
        actor_id=None,
        entity_type="quote",
        entity_id=doc.id,
        changes={"addons": doc.response.get("addons", [])},
    )
    await notifications.notify(
        session,
        settings,
        tenant_id=link.tenant_id,
        user_ids=[doc.owner_user_id],
        kind="quote.answered",
        title=title,
        link=f"/invoices/{doc.id}",
    )
    return doc.response_status


links.register_actions(LINK_ENTITY[QUOTE], _quote_action)


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


# ---------------------------------------------------------------- reminders (jobs)

REMIND_BILLING = "billing.remind"


async def enqueue_billing_reminders(session: AsyncSession) -> int:
    """Cross-tenant scan through the narrow SECURITY DEFINER function, then one job per reminder."""
    rows = (
        await session.execute(
            text(
                "SELECT tenant_id, document_id, kind, offset_days "
                "FROM app.billing_documents_due_for_reminder()"
            )
        )
    ).all()
    for tenant_id, document_id, kind, offset in rows:
        await events.enqueue(
            session,
            REMIND_BILLING,
            {
                "tenant_id": str(tenant_id),
                "document_id": str(document_id),
                "kind": kind,
                "offset_days": offset,
            },
            queueing_lock=f"billing-remind:{document_id}:{kind}:{offset}",
        )
    return len(rows)


async def send_billing_reminder(
    session: AsyncSession,
    settings: Settings,
    tenant_id: uuid.UUID,
    *,
    document_id: uuid.UUID,
    kind: str,
    offset_days: int,
) -> bool:
    """Email the client once per (document, kind, offset). Idempotent; re-checks that it still applies."""
    doc = await session.get(BillingDocument, document_id, with_for_update=True)
    tenant = await tenancy.get_tenant(session, tenant_id)
    if doc is None or doc.status != ISSUED or not tenant.billing_reminders:
        return False
    today = await tenancy.today(session, tenant_id)
    paid = (await _paid(session, [doc])).get(doc.id, ZERO) if doc.kind == INVOICE else ZERO
    state = _status(doc, paid, today)
    if (kind == "quote_expiring" and state != "sent") or (
        kind in {"due", "overdue"} and state not in {"open", "partially_paid", "overdue"}
    ):
        return False
    client = (
        await session.scalars(select(clients.Client).where(clients.Client.id == doc.client_id))
    ).one()
    inserted = await session.scalar(
        insert(BillingReminder)
        .values(
            tenant_id=tenant_id,
            document_id=doc.id,
            kind=kind,
            offset_days=offset_days,
            emailed_to=client.email,
        )
        .on_conflict_do_nothing()
        .returning(BillingReminder.id)
    )
    if inserted is None or not client.email:
        return False
    c = doc.currency
    common = {
        "recipient_name": client.first_name or client.display_name,
        "tenant_name": tenant.name,
        "number": doc.number or "",
    }
    if kind == "quote_expiring":
        event = "quote.expiring"
        context = common | {
            "valid_until": f"{doc.valid_until:%d %b %Y}" if doc.valid_until else "",
            "total": f"{c} {_round(doc.total, c):,}",
        }
    else:
        event = "invoice.reminder"
        context = common | {
            "amount_due": f"{c} {_round(doc.total - paid, c):,}",
            "due_date": f"{doc.due_date:%d %b %Y}" if doc.due_date else "",
            "payment_reference": doc.payment_reference or "",
            "overdue": "yes" if kind == "overdue" else "",
        }
    await messaging.queue_email(
        session,
        tenant_id=tenant_id,
        event=event,
        to=client.email,
        context=context,
        entity_type=LINK_ENTITY[doc.kind],
        entity_id=doc.id,
    )
    return True


# ---------------------------------------------------------------- dashboard


async def _etims_pending(ctx: TenantContext, enabled: bool) -> int:
    if not enabled:
        return 0
    stmt = _scoped(
        select(func.count()).select_from(BillingDocument),
        ctx,
        BillingDocument.owner_user_id,
    ).where(
        BillingDocument.status == ISSUED,
        BillingDocument.kind.in_([INVOICE, CREDIT_NOTE]),
        BillingDocument.etims_cu_invoice_number.is_(None),
    )
    return int(await ctx.session.scalar(stmt) or 0)


async def billing_summary(ctx: TenantContext) -> BillingSummary:
    tenant = await tenancy.get_tenant(ctx.session, ctx.tenant_id)
    currency = tenant.default_currency
    today = await tenancy.today(ctx.session, ctx.tenant_id)
    base = _scoped(select(BillingDocument), ctx, BillingDocument.owner_user_id).where(
        BillingDocument.status == ISSUED, BillingDocument.currency == currency
    )
    invoices = list((await ctx.session.scalars(base.where(BillingDocument.kind == INVOICE))).all())
    paid = await _paid(ctx.session, invoices)
    buckets = [
        ("Not yet due", 0, 0),
        ("1-30 days", 1, 30),
        ("31-60 days", 31, 60),
        ("61-90 days", 61, 90),
        ("Over 90 days", 91, 10**6),
    ]
    ageing: dict[str, list[Decimal]] = {label: [ZERO, ZERO] for label, _, _ in buckets}
    outstanding = overdue = ZERO
    overdue_count = 0
    first_month = (today.replace(day=1) - timedelta(days=330)).replace(day=1)
    months: dict[str, list[Decimal]] = {}
    cursor = first_month
    while cursor <= today:
        months[f"{cursor:%Y-%m}"] = [ZERO, ZERO]
        cursor = (cursor + timedelta(days=32)).replace(day=1)
    for doc in invoices:
        if doc.issue_date and f"{doc.issue_date:%Y-%m}" in months:
            months[f"{doc.issue_date:%Y-%m}"][0] += doc.total
        balance = doc.total - paid.get(doc.id, ZERO)
        if balance <= 0:
            continue
        outstanding += balance
        late = (today - doc.due_date).days if doc.due_date else 0
        if late > 0:
            overdue += balance
            overdue_count += 1
        label = next(label for label, low, high in buckets if low <= max(late, 0) <= high)
        ageing[label][0] += balance
        ageing[label][1] += 1
    pay_stmt = select(Payment).where(
        Payment.voided_at.is_(None),
        Payment.currency == currency,
        Payment.received_on >= first_month,
    )
    owner = own_scope(ctx.principal, Perm.CLIENT_READ_ALL)
    if owner is not None:
        pay_stmt = pay_stmt.join(clients.Client, clients.Client.id == Payment.client_id).where(
            clients.Client.owner_user_id == owner
        )
    for payment in (await ctx.session.scalars(pay_stmt)).all():
        key = f"{payment.received_on:%Y-%m}"
        if key in months:
            months[key][1] += payment.amount
    quotes = [
        q
        for q in (await ctx.session.scalars(base.where(BillingDocument.kind == QUOTE))).all()
        if _quote_status(q, today) == "sent"
    ]
    this_month = f"{today:%Y-%m}"
    return BillingSummary(
        currency=currency,
        outstanding=_round(outstanding, currency),
        overdue=_round(overdue, currency),
        overdue_count=overdue_count,
        ageing=[
            AgeingBucket(label=label, amount=_round(v[0], currency), count=int(v[1]))
            for label, v in ageing.items()
        ],
        invoiced_this_month=_round(months[this_month][0], currency),
        collected_this_month=_round(months[this_month][1], currency),
        etims_pending=await _etims_pending(ctx, tenant.etims_enabled),
        quotes_awaiting=len(quotes),
        quotes_awaiting_total=_round(sum((q.total for q in quotes), ZERO), currency),
        months=[
            MonthBilling(month=m, invoiced=_round(v[0], currency), collected=_round(v[1], currency))
            for m, v in months.items()
        ],
    )


# ---------------------------------------------------------------- for payment providers (M-Pesa)


@dataclass(frozen=True, slots=True)
class Payable:
    invoice_id: uuid.UUID
    client_id: uuid.UUID
    owner_user_id: str
    number: str | None
    payment_reference: str | None
    currency: str
    balance: Decimal
    status: str


async def payable(session: AsyncSession, invoice_id: uuid.UUID) -> Payable | None:
    """What an issued invoice still owes (None if it is not an issued invoice)."""
    doc = await session.get(BillingDocument, invoice_id)
    if doc is None or doc.kind != INVOICE or doc.status != ISSUED:
        return None
    paid = (await _paid(session, [doc])).get(doc.id, ZERO)
    return Payable(
        invoice_id=doc.id,
        client_id=doc.client_id,
        owner_user_id=doc.owner_user_id,
        number=doc.number,
        payment_reference=doc.payment_reference,
        currency=doc.currency,
        balance=max(doc.total - paid, ZERO),
        status=_status(doc, paid, await tenancy.today(session, doc.tenant_id)),
    )


async def find_by_payment_reference(session: AsyncSession, reference: str) -> uuid.UUID | None:
    """The issued invoice a client meant when typing a payment reference (case and spaces ignored)."""
    ref = numbering.normalise_payment_reference(reference)
    if not ref:
        return None
    return await session.scalar(
        select(BillingDocument.id).where(
            BillingDocument.payment_reference == ref,
            BillingDocument.kind == INVOICE,
            BillingDocument.status == ISSUED,
        )
    )


# ---------------------------------------------------------------- eTIMS (optional, ADR-0017)


class EtimsDisabledError(ConflictError):
    code = "etims_disabled"
    title = "Turn on eTIMS in the agency settings first"


async def record_etims(
    ctx: TenantContext, document_id: uuid.UUID, body: EtimsIn
) -> BillingDocument:
    """Record the KRA control-unit details the tenant's own eTIMS tool issued for this document."""
    tenant = await tenancy.get_tenant(ctx.session, ctx.tenant_id)
    if not tenant.etims_enabled:
        raise EtimsDisabledError()
    doc = await get_document(ctx, document_id, lock=True)
    if doc.kind == QUOTE or doc.status != ISSUED:
        raise BillingStateError("Only issued invoices and credit notes go to eTIMS")
    url = body.verification_url
    if url:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not (host == "kra.go.ke" or host.endswith(".kra.go.ke")):
            raise BillingInputError(
                "The verification link must be a KRA address (https://…kra.go.ke/…)"
            )
    taken = await ctx.session.scalar(
        select(BillingDocument.id).where(
            BillingDocument.etims_cu_invoice_number == body.cu_invoice_number,
            BillingDocument.id != doc.id,
        )
    )
    if taken is not None:
        raise ConflictError("That CU invoice number is already recorded on another document")
    before = doc.etims_cu_invoice_number
    doc.etims_cu_invoice_number, doc.etims_verification_url = body.cu_invoice_number, url
    doc.etims_recorded_at, doc.etims_recorded_by = datetime.now(UTC), ctx.principal.user_id
    await audit.record(
        ctx,
        f"{doc.kind}.etims_recorded",
        entity_type=doc.kind,
        entity_id=doc.id,
        changes={"before": before or "", "after": body.cu_invoice_number},
    )
    await ctx.session.flush()
    await ctx.session.refresh(doc)
    return doc
