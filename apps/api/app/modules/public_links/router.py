"""Public links: tenant management routes and anonymous ``/api/v1/public/links/{token}`` routes."""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import set_tenant_context
from app.core.errors import NotFoundError, RateLimitedError
from app.core.permissions import Perm
from app.core.ratelimit import hit
from app.modules.public_links import service
from app.modules.public_links.models import PublicLink
from app.modules.public_links.schemas import (
    ActionResult,
    Beacon,
    Choice,
    LinkCreate,
    LinkCreated,
    LinkEventOut,
    LinkOut,
    PayBody,
    PaymentAttemptOut,
    PaymentOfferOut,
    PublicLinkView,
    PublicTenant,
)
from app.modules.rendering import service as rendering
from app.modules.tenancy import service as tenancy
from app.platform.deps import ResourcesDep, TenantContext, require_permission
from app.platform.idempotency import Idempotency, idempotency_dependency

router = APIRouter(prefix="/public-links", tags=["public links"])
public_router = APIRouter(prefix="/public/links", tags=["public"])

_manage = require_permission(Perm.LINK_MANAGE)
ManageCtx = Annotated[TenantContext, Depends(_manage)]
ReadCtx = Annotated[TenantContext, Depends(require_permission(Perm.DOCUMENT_READ))]


@router.post("", operation_id="public_links_create", status_code=201, response_model=LinkCreated)
async def create_link(
    ctx: ManageCtx,
    body: LinkCreate,
    resources: ResourcesDep,
    idem: Annotated[Idempotency, Depends(idempotency_dependency(_manage))],
) -> Response:
    if (replay := await idem.replay()) is not None:
        return replay
    link, token = await service.create_link(ctx, body, resources.settings, resources.storage)
    out = LinkCreated(
        **LinkOut.model_validate(link).model_dump(),
        message_id=link.sent_message_id,
        url=service.link_url(token, resources.settings),
        token=token,
    )
    return await idem.respond(201, out)


@router.get("", operation_id="public_links_list")
async def list_links(
    ctx: ReadCtx,
    entity_type: Annotated[str | None, Query(max_length=40)] = None,
    entity_id: uuid.UUID | None = None,
) -> list[LinkOut]:
    return [
        LinkOut.model_validate(x)
        for x in await service.list_links(ctx.session, entity_type, entity_id)
    ]


@router.post("/{link_id}/revoke", operation_id="public_links_revoke")
async def revoke(ctx: ManageCtx, link_id: uuid.UUID) -> LinkOut:
    """Takes effect immediately: the next request with the token gets 410."""
    return LinkOut.model_validate(await service.revoke(ctx, link_id))


@router.get("/{link_id}/events", operation_id="public_links_events")
async def link_events(ctx: ReadCtx, link_id: uuid.UUID) -> list[LinkEventOut]:
    return [LinkEventOut.model_validate(e) for e in await service.events(ctx.session, link_id)]


# ---------------------------------------------------------------- anonymous


@dataclass(frozen=True, slots=True)
class PublicContext:
    session: AsyncSession
    link: PublicLink
    ip_hash: str | None
    user_agent: str | None


Token = Annotated[str, Path(min_length=10, max_length=100)]


async def _public_context(
    token: Token, request: Request, resources: ResourcesDep
) -> AsyncIterator[PublicContext]:
    settings = resources.settings
    ip = request.client.host if request.client else None
    decision = await hit(
        resources.valkey, f"public:{ip}", limit=settings.public_rate_limit_per_minute
    )
    if not decision.allowed:
        raise RateLimitedError(decision.retry_after_seconds)
    async with resources.session_factory() as session, session.begin():
        tenant_id, link_id = await service.resolve(session, token)
        await set_tenant_context(session, tenant_id)
        link = await service.load_active(session, link_id)
        yield PublicContext(
            session=session,
            link=link,
            ip_hash=service.hash_ip(ip, settings),
            user_agent=request.headers.get("user-agent"),
        )


Public = Annotated[PublicContext, Depends(_public_context, scope="function")]
_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Robots-Tag": "noindex, nofollow",
}


@public_router.get("/{token}", operation_id="public_link_get")
async def get_public(ctx: Public, resources: ResourcesDep, response: Response) -> PublicLinkView:
    content = await service.content(ctx.session, resources.storage, resources.settings, ctx.link)
    tenant = await tenancy.get_tenant(ctx.session, ctx.link.tenant_id)
    await service.record_event(
        ctx.session, ctx.link, "opened", ip_hash=ctx.ip_hash, user_agent=ctx.user_agent
    )
    response.headers.update(_SECURITY_HEADERS)
    return PublicLinkView(
        tenant=PublicTenant(name=tenant.name),
        title=content.title,
        kind=content.kind,
        scopes=ctx.link.scopes,
        expires_at=ctx.link.expires_at,
        has_web_view=content.html is not None,
        has_download=content.download is not None,
        state=content.state,
        choices=[Choice(**c) for c in content.choices],
        payment=PaymentOfferOut(amount=offer.amount, currency=offer.currency, methods=offer.methods)
        if (offer := await service.payment_offer(ctx.session, resources.settings, ctx.link))
        else None,
    )


@public_router.get("/{token}/html", operation_id="public_link_html", response_class=HTMLResponse)
async def get_public_html(ctx: Public, resources: ResourcesDep) -> HTMLResponse:
    """Self-contained HTML for a sandboxed iframe (no scripts, no network; strict CSP)."""
    content = await service.content(ctx.session, resources.storage, resources.settings, ctx.link)
    if content.html is None:
        raise NotFoundError("This link has no web view")
    frame_ancestors = resources.settings.public_base_url.rstrip("/")
    headers = {
        **_SECURITY_HEADERS,
        "Content-Security-Policy": rendering.CSP.replace(
            "frame-ancestors *", f"frame-ancestors {frame_ancestors}"
        ),
    }
    return HTMLResponse(await content.html(), headers=headers)


@public_router.get(
    "/{token}/download",
    operation_id="public_link_download",
    status_code=302,
    response_class=RedirectResponse,
)
async def download(ctx: Public, resources: ResourcesDep) -> RedirectResponse:
    content = await service.content(ctx.session, resources.storage, resources.settings, ctx.link)
    if content.download is None:
        raise NotFoundError("Nothing to download")
    url = await content.download()
    await service.record_event(
        ctx.session, ctx.link, "downloaded", ip_hash=ctx.ip_hash, user_agent=ctx.user_agent
    )
    return RedirectResponse(url, status_code=302, headers=_SECURITY_HEADERS)


@public_router.post("/{token}/beacon", operation_id="public_link_beacon", status_code=204)
async def beacon(ctx: Public, body: Beacon, resources: ResourcesDep) -> None:
    """Sent by the public page after it rendered. Only this counts as a view; bots are recorded, not counted."""
    details: dict[str, object] = {}
    if body.duration_ms is not None:
        details["duration_ms"] = body.duration_ms
    await service.record_event(
        ctx.session,
        ctx.link,
        "viewed",
        ip_hash=ctx.ip_hash,
        user_agent=ctx.user_agent,
        details=details,
        storage=resources.storage,
        settings=resources.settings,
    )


@public_router.post("/{token}/accept", operation_id="public_link_accept")
async def accept(ctx: Public, body: dict[str, Any], resources: ResourcesDep) -> ActionResult:
    """Accept (e.g. one option of a quotation). Requires the link's `accept` scope; recorded as evidence."""
    state = await service.perform(
        ctx.session,
        resources.settings,
        ctx.link,
        "accept",
        body,
        ip_hash=ctx.ip_hash,
        user_agent=ctx.user_agent,
    )
    return ActionResult(state=state)


@public_router.post("/{token}/decline", operation_id="public_link_decline")
async def decline(ctx: Public, body: dict[str, Any], resources: ResourcesDep) -> ActionResult:
    state = await service.perform(
        ctx.session,
        resources.settings,
        ctx.link,
        "decline",
        body,
        ip_hash=ctx.ip_hash,
        user_agent=ctx.user_agent,
    )
    return ActionResult(state=state)


@public_router.post("/{token}/pay", operation_id="public_link_pay")
async def pay(ctx: Public, body: PayBody, resources: ResourcesDep) -> PaymentAttemptOut:
    """Send a payment prompt to the client's phone (the link needs the `pay` scope)."""
    payer = service.payer_for(ctx.link)
    decision = await hit(resources.valkey, f"pay:{ctx.link.id}", limit=5)
    if not decision.allowed:
        raise RateLimitedError(decision.retry_after_seconds)
    attempt = await payer.start(
        session=ctx.session,
        settings=resources.settings,
        http=resources.http,
        link=ctx.link,
        phone=body.phone,
    )
    await service.record_event(
        ctx.session, ctx.link, "payment_started", ip_hash=ctx.ip_hash, user_agent=ctx.user_agent
    )
    return PaymentAttemptOut(
        attempt_id=attempt.attempt_id, status=attempt.status, message=attempt.message
    )


@public_router.get("/{token}/pay/{attempt_id}", operation_id="public_link_pay_status")
async def pay_status(
    ctx: Public, attempt_id: uuid.UUID, resources: ResourcesDep
) -> PaymentAttemptOut:
    """Poll a payment prompt; asks M-Pesa directly when its callback is late."""
    attempt = await service.payer_for(ctx.link).status(
        session=ctx.session,
        settings=resources.settings,
        http=resources.http,
        link=ctx.link,
        attempt_id=attempt_id,
    )
    return PaymentAttemptOut(
        attempt_id=attempt.attempt_id, status=attempt.status, message=attempt.message
    )
