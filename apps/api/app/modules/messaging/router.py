"""Messaging endpoints: outbound log, templates, test email, and the public unsubscribe page."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import HTMLResponse

from app.core.db import tenant_scope
from app.core.pagination import Page, PageParams, build_page, page_params
from app.core.permissions import Perm
from app.modules.messaging import service
from app.modules.messaging.schemas import MessageOut, TemplateOut, TemplateOverride
from app.modules.tenancy import service as tenancy
from app.platform.deps import ResourcesDep, TenantContext, require_permission

router = APIRouter(tags=["messaging"])
public_router = APIRouter(prefix="/public/unsubscribe", tags=["public"])

ReadCtx = Annotated[TenantContext, Depends(require_permission(Perm.MESSAGE_READ))]
ManageCtx = Annotated[TenantContext, Depends(require_permission(Perm.MESSAGE_TEMPLATE_MANAGE))]
Locale = Annotated[str, Path(pattern=r"^[a-z]{2}$")]


@router.get("/messages", operation_id="messages_list")
async def list_messages(
    ctx: ReadCtx,
    page: Annotated[PageParams, Depends(page_params)],
    entity_type: Annotated[str | None, Query(max_length=40)] = None,
    entity_id: uuid.UUID | None = None,
) -> Page[MessageOut]:
    rows = await service.list_messages(
        ctx.session,
        cursor=page.cursor,
        limit=page.limit,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    return build_page(
        [MessageOut.model_validate(r) for r in rows], [r.id for r in rows], page.limit
    )


@router.post("/messages/test-email", operation_id="messages_test_email", status_code=202)
async def test_email(ctx: ManageCtx) -> MessageOut:
    """Send a test email to yourself (checks delivery and the tenant's From/Reply-To)."""
    tenant = await tenancy.get_tenant(ctx.session, ctx.tenant_id)
    message = await service.queue_email(
        ctx.session,
        tenant_id=ctx.tenant_id,
        event="test.email",
        to=ctx.principal.email,
        context={
            "recipient_name": ctx.principal.name or ctx.principal.email,
            "tenant_name": tenant.name,
        },
        actor=ctx.principal.user_id,
    )
    return MessageOut.model_validate(message)


@router.get("/message-templates", operation_id="message_templates_list")
async def list_templates(ctx: ReadCtx) -> list[TemplateOut]:
    return await service.list_templates(ctx.session)


@router.put("/message-templates/{event}/{locale}", operation_id="message_templates_set")
async def set_template(
    ctx: ManageCtx, event: str, locale: Locale, body: TemplateOverride
) -> TemplateOut:
    return await service.set_override(ctx, event, locale, body)


@router.delete(
    "/message-templates/{event}/{locale}", operation_id="message_templates_reset", status_code=204
)
async def reset_template(ctx: ManageCtx, event: str, locale: Locale) -> None:
    await service.reset_override(ctx, event, locale)


_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Unsubscribe</title></head>
<body style="font-family:Arial,sans-serif;max-width:32rem;margin:3rem auto;padding:0 1rem">{body}</body></html>"""
_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'",
    "Cache-Control": "no-store",
    "X-Robots-Tag": "noindex",
}
Token = Annotated[str, Path(min_length=10, max_length=400)]


@public_router.get("/{token}", operation_id="unsubscribe_page", response_class=HTMLResponse)
async def unsubscribe_page(token: Token, resources: ResourcesDep) -> HTMLResponse:
    service.read_unsubscribe_token(token, resources.settings)  # 404 on a forged link
    body = (
        "<h1>Unsubscribe from reminders?</h1>"
        '<form method="post"><button type="submit">Unsubscribe</button></form>'
    )
    return HTMLResponse(_PAGE.format(body=body), headers=_HEADERS)


@public_router.post("/{token}", operation_id="unsubscribe", response_class=HTMLResponse)
async def unsubscribe(token: Token, resources: ResourcesDep) -> HTMLResponse:
    """One-click unsubscribe (RFC 8058) and the form above both land here."""
    tenant_id, email, stream = service.read_unsubscribe_token(token, resources.settings)
    async with tenant_scope(resources.session_factory, tenant_id) as session:
        await service.suppress(session, tenant_id, email, stream, "unsubscribed")
    return HTMLResponse(
        _PAGE.format(
            body="<h1>You are unsubscribed.</h1><p>You will not get these reminders again.</p>"
        ),
        headers=_HEADERS,
    )
