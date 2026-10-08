"""Quote endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel

from app.core.concurrency import etag
from app.core.permissions import Perm
from app.modules.quotes import service
from app.modules.quotes.schemas import (
    QuoteCreate,
    QuoteOut,
    QuoteRecalculate,
    QuoteSummary,
    SendQuote,
    Sent,
)
from app.platform.deps import ResourcesDep, TenantContext, require_permission
from app.platform.idempotency import Idempotency, idempotency_dependency

router = APIRouter(prefix="/quotes", tags=["quotes"])
_write = require_permission(Perm.CLIENT_WRITE)
Read = Annotated[
    TenantContext, Depends(require_permission((Perm.CLIENT_READ_OWN, Perm.CLIENT_READ_ALL)))
]
Write = Annotated[TenantContext, Depends(_write)]


class PdfLink(BaseModel):
    url: str


@router.get("", operation_id="quotes_list")
async def list_quotes(
    ctx: Read,
    client_id: uuid.UUID | None = None,
    status: Annotated[str | None, Query(max_length=20)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[QuoteSummary]:
    return await service.list_quotes(ctx, client_id=client_id, status=status, limit=limit)


@router.post("", operation_id="quotes_create", status_code=201, response_model=QuoteOut)
async def create_quote(
    ctx: Write,
    body: QuoteCreate,
    idem: Annotated[Idempotency, Depends(idempotency_dependency(_write))],
) -> Response:
    """Price the risk with each product and save a draft quote (options cheapest first)."""
    if (replay := await idem.replay()) is not None:
        return replay
    quote = await service.create_quote(ctx, body)
    return await idem.respond(201, await service.to_out(ctx, quote), {"ETag": etag(quote.version)})


@router.get("/{quote_id}", operation_id="quotes_get")
async def get_quote(ctx: Read, quote_id: uuid.UUID, response: Response) -> QuoteOut:
    quote = await service.get_quote(ctx, quote_id)
    response.headers["ETag"] = etag(quote.version)
    return await service.to_out(ctx, quote)


@router.put("/{quote_id}/options", operation_id="quotes_recalculate")
async def recalculate(
    ctx: Write,
    quote_id: uuid.UUID,
    body: QuoteRecalculate,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
) -> QuoteOut:
    """Re-price a draft with new products or risk details."""
    quote = await service.recalculate(ctx, quote_id, body, if_match)
    response.headers["ETag"] = etag(quote.version)
    return await service.to_out(ctx, quote)


@router.post("/{quote_id}/send", operation_id="quotes_send")
async def send(ctx: Write, quote_id: uuid.UUID, body: SendQuote, resources: ResourcesDep) -> Sent:
    """Number the quote, render the PDF, create the tracked link and (if there is an email) send it."""
    quote, url, emailed = await service.send(
        ctx,
        quote_id,
        body,
        settings=resources.settings,
        storage=resources.storage,
        renderer=resources.pdf_renderer,
    )
    out = await service.to_out(ctx, quote)
    whatsapp = None
    if out.client.phone:
        from urllib.parse import quote as urlquote  # noqa: PLC0415

        text = f"Hello {out.client.display_name}, here is your quotation {out.number}: {url}"
        whatsapp = f"https://wa.me/{out.client.phone.lstrip('+')}?text={urlquote(text)}"
    return Sent(quote=out, url=url, emailed_to=emailed, whatsapp_url=whatsapp)


@router.post("/{quote_id}/withdraw", operation_id="quotes_withdraw")
async def withdraw(ctx: Write, quote_id: uuid.UUID) -> QuoteOut:
    """Withdraw a quote: its link stops working immediately."""
    return await service.to_out(ctx, await service.withdraw(ctx, quote_id))


@router.get("/{quote_id}/pdf", operation_id="quotes_pdf")
async def pdf(ctx: Read, quote_id: uuid.UUID, resources: ResourcesDep) -> PdfLink:
    return PdfLink(url=await service.pdf_url(ctx, quote_id, resources.storage, resources.settings))
