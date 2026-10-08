"""Insurance quotes (Plan A1.1 R1.3).

A quote is a client + a risk + 1..8 insurer options. Each option freezes the calculator's output (breakdown,
pack version, notes) so later rate or pack changes never alter what the client was offered. Commission is kept
on the option for the agent and never serialised into anything client-facing (public page, PDF, emails).

Lifecycle: draft (recalculate freely) → sent (number allocated, PDF rendered, tracked link) → accepted |
declined (by the client on the link) | withdrawn (by the agency). A sent quote past ``valid_until`` reads as
"expired" and can no longer be accepted.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from http import HTTPStatus
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Select, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.concurrency import check_version
from app.core.config import Settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.money import Money
from app.core.permissions import Perm
from app.integrations.pdf import PdfRenderer
from app.integrations.storage.s3 import S3Storage
from app.modules.clients import service as clients
from app.modules.documents import service as documents
from app.modules.insurers import service as insurers
from app.modules.leads import service as leads
from app.modules.notifications import service as notifications
from app.modules.numbering import service as numbering
from app.modules.public_links import service as links
from app.modules.quotes.models import Quote, QuoteOption
from app.modules.quotes.schemas import (
    AcceptBody,
    ClientRef,
    DeclineBody,
    OptionOut,
    QuoteCreate,
    QuoteOut,
    QuoteRecalculate,
    QuoteSummary,
    SendQuote,
)
from app.modules.rendering import service as rendering
from app.modules.rendering.service import AmountLine, DocumentView, KeyValue, OptionView, Party
from app.modules.tenancy import service as tenancy
from app.platform import audit
from app.platform.deps import TenantContext, own_scope

DRAFT, SENT, ACCEPTED, DECLINED, WITHDRAWN, EXPIRED = (
    "draft",
    "sent",
    "accepted",
    "declined",
    "withdrawn",
    "expired",
)


class QuoteStateError(ConflictError):
    code = "quote_state"
    title = "The quote cannot do that in its current state"


class MultiInsurerDisabledError(AppError):
    status = HTTPStatus.UNPROCESSABLE_CONTENT
    code = "multi_insurer_disabled"
    title = "Your agency quotes one insurer at a time"


class QuoteNotReadyError(AppError):
    status = HTTPStatus.UNPROCESSABLE_CONTENT
    code = "quote_incomplete"
    title = "Some options still need details before the quote can be sent"


# ---------------------------------------------------------------- helpers


async def _today(session: AsyncSession, tenant_id: uuid.UUID) -> date:
    tenant = await tenancy.get_tenant(session, tenant_id)
    return datetime.now(ZoneInfo(tenant.timezone)).date()


def effective_status(quote: Quote, today: date) -> str:
    return EXPIRED if quote.status == SENT and quote.valid_until < today else quote.status


def _scoped_stmt(ctx: TenantContext) -> Select[Quote]:
    owner = own_scope(ctx.principal, Perm.CLIENT_READ_ALL)
    stmt = select(Quote)
    return stmt if owner is None else stmt.where(Quote.owner_user_id == owner)


async def get_quote(ctx: TenantContext, quote_id: uuid.UUID) -> Quote:
    quote = (await ctx.session.scalars(_scoped_stmt(ctx).where(Quote.id == quote_id))).first()
    if quote is None:
        raise NotFoundError("Quote not found")
    return quote


async def _options(session: AsyncSession, quote_id: uuid.UUID) -> list[QuoteOption]:
    stmt = (
        select(QuoteOption).where(QuoteOption.quote_id == quote_id).order_by(QuoteOption.position)
    )
    return list((await session.scalars(stmt)).all())


async def _build_options(
    ctx: TenantContext, quote: Quote, body: QuoteCreate | QuoteRecalculate
) -> None:
    tenant = await tenancy.get_tenant(ctx.session, ctx.tenant_id)
    product_ids = list(dict.fromkeys(body.product_ids))
    if len(product_ids) > 1 and not tenant.multi_insurer_quotes:
        raise MultiInsurerDisabledError(
            "Choose one product, or allow comparison quotes in the agency profile"
        )
    priced: list[tuple[insurers.Product, Any, insurers.CalculationOut]] = []
    for product_id in product_ids:
        product = await insurers.get_product(ctx, product_id)
        result, out = await insurers.calculate_product(ctx, product, body.risk)
        priced.append((product, result, out))
    classes = {p.class_code for p, _, _ in priced}
    currencies = {p.currency for p, _, _ in priced}
    if len(classes) > 1 or len(currencies) > 1:
        raise AppError("All options in a quote must be the same class of business and currency")
    priced.sort(key=lambda item: (bool(item[1].needs_input), item[1].client_total))
    await ctx.session.execute(delete(QuoteOption).where(QuoteOption.quote_id == quote.id))
    for position, (product, result, out) in enumerate(priced, start=1):
        breakdown = out.model_dump(mode="json", exclude={"commission"})
        ctx.session.add(
            QuoteOption(
                tenant_id=ctx.tenant_id,
                quote_id=quote.id,
                position=position,
                product_id=product.id,
                insurer_name=out.product.insurer_name,
                product_name=product.name,
                excess_text=product.excess_text,
                breakdown=breakdown,
                client_total=result.client_total,
                commission=result.commission.model_dump(mode="json") if result.commission else None,
                needs_input=bool(result.needs_input),
                recommended=product.id == body.recommended_product_id,
            )
        )
    quote.class_code = classes.pop()
    quote.currency = currencies.pop()
    quote.risk = body.risk.model_dump(mode="json")
    await ctx.session.flush()


async def _summary(
    ctx: TenantContext, quote: Quote, options: list[QuoteOption], today: date
) -> dict[str, Any]:
    client = await clients.get_visible_client(ctx, quote.client_id)
    totals = [
        Money(o.client_total, quote.currency).rounded().amount for o in options if not o.needs_input
    ]
    return {
        "id": quote.id,
        "number": quote.number,
        "title": quote.title,
        "client": ClientRef(
            id=client.id, display_name=client.display_name, email=client.email, phone=client.phone
        ),
        "class_code": quote.class_code,
        "currency": quote.currency,
        "status": effective_status(quote, today),
        "valid_until": quote.valid_until,
        "lowest_total": min(totals) if totals else None,
        "options": len(options),
        "owner_user_id": quote.owner_user_id,
        "created_at": quote.created_at,
    }


async def to_out(ctx: TenantContext, quote: Quote) -> QuoteOut:
    options = await _options(ctx.session, quote.id)
    today = await _today(ctx.session, ctx.tenant_id)
    show = insurers.can_see_commission(ctx)
    return QuoteOut(
        **await _summary(ctx, quote, options, today),
        risk=quote.risk,
        details=quote.details,  # type: ignore[arg-type]
        notes=quote.notes,
        sent_at=quote.sent_at,
        accepted_position=quote.accepted_position,
        responded_at=quote.responded_at,
        response=quote.response,
        document_id=quote.document_id,
        option_list=[
            OptionOut(
                position=o.position,
                product_id=o.product_id,
                insurer_name=o.insurer_name,
                product_name=o.product_name,
                excess_text=o.excess_text,
                client_total=Money(o.client_total, quote.currency).rounded().amount,
                breakdown=o.breakdown,
                commission=o.commission if show else None,
                needs_input=o.needs_input,
                recommended=o.recommended,
            )
            for o in options
        ],
        version=quote.version,
    )


# ---------------------------------------------------------------- create / edit


async def create_quote(ctx: TenantContext, body: QuoteCreate) -> Quote:
    client = await clients.get_visible_client(ctx, body.client_id)
    pack, _, _ = await insurers.agency_pack(ctx)
    quote = Quote(
        tenant_id=ctx.tenant_id,
        client_id=client.id,
        owner_user_id=client.owner_user_id or ctx.principal.user_id,
        class_code="pending",
        title=body.title or "",
        risk={},
        details=[d.model_dump() for d in body.details],
        notes=body.notes,
        valid_until=await _today(ctx.session, ctx.tenant_id) + timedelta(days=body.valid_days),
        created_by=ctx.principal.user_id,
        updated_by=ctx.principal.user_id,
    )
    ctx.session.add(quote)
    await ctx.session.flush()
    await _build_options(ctx, quote, body)
    if not quote.title:
        klass = pack.insurance_class(quote.class_code)
        quote.title = f"{klass.name if klass else quote.class_code} quotation"
    await ctx.session.flush()
    await ctx.session.refresh(quote)
    await audit.record(
        ctx,
        "quote.created",
        entity_type="quote",
        entity_id=quote.id,
        changes={"client_id": str(client.id), "options": len(body.product_ids)},
    )
    return quote


async def recalculate(
    ctx: TenantContext, quote_id: uuid.UUID, body: QuoteRecalculate, if_match: str | None
) -> Quote:
    quote = await get_quote(ctx, quote_id)
    check_version(if_match, quote.version)
    if quote.status != DRAFT:
        raise QuoteStateError("Only draft quotes can be changed; create a new quote instead")
    await _build_options(ctx, quote, body)
    if body.details is not None:
        quote.details = [d.model_dump() for d in body.details]
    if body.notes is not None:
        quote.notes = body.notes
    quote.updated_by = ctx.principal.user_id
    await ctx.session.flush()
    await ctx.session.refresh(quote)
    return quote


async def list_quotes(
    ctx: TenantContext, *, client_id: uuid.UUID | None, status: str | None, limit: int
) -> list[QuoteSummary]:
    stmt = _scoped_stmt(ctx).order_by(Quote.id.desc()).limit(limit)
    if client_id is not None:
        stmt = stmt.where(Quote.client_id == client_id)
    if status in {DRAFT, SENT, ACCEPTED, DECLINED, WITHDRAWN}:
        stmt = stmt.where(Quote.status == status)
    today = await _today(ctx.session, ctx.tenant_id)
    rows = list((await ctx.session.scalars(stmt)).all())
    out = [
        QuoteSummary(**await _summary(ctx, quote, await _options(ctx.session, quote.id), today))
        for quote in rows
    ]
    if status == EXPIRED:
        out = [q for q in out if q.status == EXPIRED]
    return out


# ---------------------------------------------------------------- document


async def document_view(session: AsyncSession, tenant_id: uuid.UUID, quote: Quote) -> DocumentView:
    tenant = await tenancy.get_tenant(session, tenant_id)
    options = await _options(session, quote.id)
    client = (
        await session.scalars(select(clients.Client).where(clients.Client.id == quote.client_id))
    ).one()
    pack_ref = options[0].breakdown.get("pack", {}) if options else {}

    def option_view(o: QuoteOption) -> OptionView:
        lines = o.breakdown["lines"]
        premium = sum(
            (
                Decimal(line["amount"])
                for line in lines
                if line["kind"] in {"premium", "benefit", "loading", "discount"}
                and line["charged_to"] == "client"
            ),
            Decimal(0),
        )
        charges = [
            AmountLine(label=line["label"], amount=Decimal(line["amount"]))
            for line in lines
            if line["kind"] in {"levy", "stamp_duty", "fee", "fee_tax"}
            and line["charged_to"] == "client"
        ]
        return OptionView(
            position=o.position,
            insurer=o.insurer_name,
            product=o.product_name,
            premium=premium,
            charges=charges,
            total=o.client_total,
            excess=o.excess_text,
            recommended=o.recommended,
        )

    terms = f"Valid until {quote.valid_until:%d %b %Y}. Cover starts only once the insurer confirms it and the premium is paid."
    if pack_ref and not pack_ref.get("signed", True):
        terms += " Statutory levies are computed from published rates and confirmed by the insurer on cover."
    return DocumentView(
        doc_type="quote",
        number=quote.number,
        issue_date=(quote.sent_at or datetime.now(UTC)).date(),
        valid_until=quote.valid_until,
        currency=quote.currency,
        seller=Party(
            name=tenant.name, tax_pin=tenant.tax_pin, email=tenant.email, phone=tenant.phone
        ),
        buyer=Party(
            name=client.display_name, email=client.email, phone=client.phone, tax_pin=client.kra_pin
        ),
        details=[KeyValue(label=d["label"], value=d["value"]) for d in quote.details],
        options=[option_view(o) for o in options],
        notes=quote.notes,
        terms=terms,
        stamp="DRAFT" if quote.status == DRAFT else None,
    )


# ---------------------------------------------------------------- send / withdraw


async def send(
    ctx: TenantContext,
    quote_id: uuid.UUID,
    body: SendQuote,
    *,
    settings: Settings,
    storage: S3Storage,
    renderer: PdfRenderer,
) -> tuple[Quote, str, str | None]:
    quote = await get_quote(ctx, quote_id)
    today = await _today(ctx.session, ctx.tenant_id)
    if effective_status(quote, today) not in {DRAFT, SENT}:
        raise QuoteStateError(f"A {effective_status(quote, today)} quote cannot be sent")
    options = await _options(ctx.session, quote.id)
    if not options or any(o.needs_input for o in options):
        raise QuoteNotReadyError(
            "Enter the missing details (e.g. stamp duty) and recalculate first"
        )
    if quote.number is None:
        quote.number = (
            await numbering.allocate_number(ctx.session, ctx.tenant_id, "quote", on=today)
        ).number
    quote.status = SENT
    quote.sent_at = quote.sent_at or datetime.now(UTC)
    await ctx.session.flush()
    view = await document_view(ctx.session, ctx.tenant_id, quote)
    pdf = await rendering.generate_pdf(
        ctx.session,
        storage,
        renderer,
        tenant_id=ctx.tenant_id,
        view=view,
        entity=documents.EntityRef(entity_type="quote", entity_id=quote.id),
        actor=ctx.principal.user_id,
    )
    quote.document_id = pdf.id
    client = await clients.get_visible_client(ctx, quote.client_id)
    email = str(body.email) if body.email else client.email
    days = max((quote.valid_until - today).days, 1)
    _, token = await links.create_link(
        ctx,
        links.LinkCreate(
            entity_type="quote",
            entity_id=quote.id,
            scopes=["view", "accept"],
            expires_in_days=min(days + 7, 365),
            send_to=links.SendTo(email=email, name=client.display_name, message=body.message)
            if email
            else None,
        ),
        settings,
        storage,
    )
    await leads.mark_quoted(ctx, client.id)
    await audit.record(
        ctx,
        "quote.sent",
        entity_type="quote",
        entity_id=quote.id,
        changes={"number": quote.number, "emailed_to": email or ""},
    )
    await ctx.session.flush()
    await ctx.session.refresh(quote)
    return quote, links.link_url(token, settings), email


async def withdraw(ctx: TenantContext, quote_id: uuid.UUID) -> Quote:
    quote = await get_quote(ctx, quote_id)
    if quote.status not in {DRAFT, SENT}:
        raise QuoteStateError(f"A {quote.status} quote cannot be withdrawn")
    quote.status = WITHDRAWN
    await links.revoke_for_entity(ctx, "quote", quote.id)
    await audit.record(ctx, "quote.withdrawn", entity_type="quote", entity_id=quote.id)
    await ctx.session.flush()
    await ctx.session.refresh(quote)
    return quote


async def pdf_url(
    ctx: TenantContext, quote_id: uuid.UUID, storage: S3Storage, settings: Settings
) -> str:
    quote = await get_quote(ctx, quote_id)
    if quote.document_id is None:
        raise ConflictError("Send the quote first; the PDF is created when it is sent")
    return (
        await documents.download_url(ctx.session, quote.document_id, storage, settings, inline=True)
    ).url


# ---------------------------------------------------------------- public link target & actions


async def _public_target(
    session: AsyncSession, storage: S3Storage, settings: Settings, link: links.PublicLink
) -> links.PublicContent:
    quote = (await session.scalars(select(Quote).where(Quote.id == link.entity_id))).first()
    if quote is None or quote.status == WITHDRAWN:
        raise links.LinkGoneError()
    today = await _today(session, link.tenant_id)
    options = await _options(session, quote.id)

    async def html() -> str:
        view = await document_view(session, link.tenant_id, quote)
        return await rendering.render_html_for(session, storage, link.tenant_id, view)

    async def download() -> str:
        if quote.document_id is None:
            raise links.LinkGoneError()
        return (
            await documents.download_url(session, quote.document_id, storage, settings, inline=True)
        ).url

    return links.PublicContent(
        title=f"Quotation {quote.number or ''}".strip(),
        kind="quote",
        html=html,
        download=download if quote.document_id else None,
        state=effective_status(quote, today),
        choices=[
            {
                "position": o.position,
                "label": f"{o.insurer_name}: {o.product_name}",
                "amount": str(o.client_total),
                "currency": quote.currency,
                "recommended": o.recommended,
            }
            for o in options
        ],
    )


async def _public_action(
    *,
    session: AsyncSession,
    settings: Settings,
    link: links.PublicLink,
    action: str,
    body: dict[str, Any],
    evidence: dict[str, Any],
) -> str:
    quote = (
        await session.scalars(select(Quote).where(Quote.id == link.entity_id).with_for_update())
    ).first()
    if quote is None:
        raise links.LinkGoneError()
    state = effective_status(quote, await _today(session, link.tenant_id))
    if state != SENT:
        raise QuoteStateError(f"This quotation is {state} and can no longer be answered")
    now = datetime.now(UTC)
    if action == "accept":
        accepted = AcceptBody.model_validate(body)
        options = {o.position: o for o in await _options(session, quote.id)}
        if accepted.option not in options:
            raise NotFoundError("That option is not on this quotation")
        quote.status, quote.accepted_position = ACCEPTED, accepted.option
        quote.response = {
            "action": "accept",
            "option": accepted.option,
            "name": accepted.name,
            "phone": accepted.phone,
            "email": str(accepted.email) if accepted.email else None,
            "agreed_terms": True,
            **evidence,
        }
        title = f"{accepted.name} accepted quotation {quote.number}: {options[accepted.option].insurer_name}"
    else:
        declined = DeclineBody.model_validate(body)
        quote.status = DECLINED
        quote.response = {"action": "decline", "reason": declined.reason, **evidence}
        title = f"Quotation {quote.number} was declined"
    quote.responded_at = now
    await audit.record_actor(
        session,
        link.tenant_id,
        f"quote.{quote.status}",
        actor_type="client",
        actor_id=None,
        entity_type="quote",
        entity_id=quote.id,
        changes={"option": quote.accepted_position},
    )
    await notifications.notify(
        session,
        settings,
        tenant_id=link.tenant_id,
        user_ids=[quote.owner_user_id],
        kind="quote.answered",
        title=title,
        link=f"/quotes/{quote.id}",
    )
    return quote.status


links.register_target("quote", _public_target)
links.register_actions("quote", _public_action)
