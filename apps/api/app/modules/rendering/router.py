"""Templates catalogue, tenant branding and live preview."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response

from app.core.concurrency import etag
from app.core.errors import NotFoundError
from app.core.permissions import Perm
from app.modules.rendering import engine, service
from app.modules.rendering.fixtures import sample_view
from app.modules.rendering.schemas import (
    BrandingOut,
    BrandingUpdate,
    TemplateOut,
    TemplatePreviewRequest,
)
from app.modules.subscriptions.service import Feature
from app.modules.tenancy import service as tenancy
from app.platform.deps import ResourcesDep, TenantContext, require_feature, require_permission

router = APIRouter(tags=["branding"])
ReadCtx = Annotated[TenantContext, Depends(require_permission(Perm.ORG_READ))]


@router.get("/templates", operation_id="templates_list")
async def list_templates(ctx: ReadCtx) -> list[TemplateOut]:
    return [TemplateOut.model_validate(m.model_dump()) for m in service.template_catalog()]


@router.post(
    "/templates/{key}/preview",
    operation_id="templates_preview",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}, "text/html": {}}}},
)
async def preview(
    key: str, body: TemplatePreviewRequest, ctx: ReadCtx, resources: ResourcesDep
) -> Response:
    """Render sample data with this template and the tenant's branding (or unsaved `branding` overrides)."""
    if key not in engine.catalog():
        raise NotFoundError(f"Template {key!r} not found")
    row = await service.get_branding(ctx.session, ctx.tenant_id)
    tenant = await tenancy.get_tenant(ctx.session, ctx.tenant_id)
    sample = sample_view(body.doc_type, body.variant, seller_name=tenant.name)
    view = service.with_payment_defaults(sample, row)
    branding = await service.branding_view(
        ctx.session, resources.storage, row, key, overrides=body.branding
    )
    content = await service.render(resources.pdf_renderer, key, view, branding, body.format)
    media_type = "application/pdf" if body.format == "pdf" else "text/html; charset=utf-8"
    headers = {"Content-Security-Policy": engine.CSP, "X-Content-Type-Options": "nosniff"}
    return Response(content, media_type=media_type, headers=headers)


@router.get("/branding", operation_id="branding_get")
async def get_branding(ctx: ReadCtx, response: Response) -> BrandingOut:
    row = await service.get_branding(ctx.session, ctx.tenant_id)
    response.headers["ETag"] = etag(row.version)
    return service.branding_out(row)


@router.patch(
    "/branding",
    operation_id="branding_update",
    dependencies=[Depends(require_feature(Feature.BRANDING))],
)
async def update_branding(
    ctx: Annotated[TenantContext, Depends(require_permission(Perm.BRANDING_MANAGE))],
    body: BrandingUpdate,
    response: Response,
    resources: ResourcesDep,
    if_match: Annotated[str | None, Header()] = None,
) -> BrandingOut:
    row = await service.update_branding(ctx, resources.storage, body, if_match)
    response.headers["ETag"] = etag(row.version)
    return service.branding_out(row)
