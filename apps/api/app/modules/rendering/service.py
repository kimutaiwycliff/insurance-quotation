"""Rendering service: branding, template choice, HTML/PDF rendering and cached generated PDFs (ADR-0014)."""

import base64
import hashlib
import json
import uuid
from http import HTTPStatus
from typing import Any, Literal, cast

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.concurrency import check_version
from app.core.errors import AppError, NotFoundError
from app.integrations.pdf import PdfRenderer
from app.integrations.storage.s3 import S3Storage
from app.modules.documents import service as documents
from app.modules.documents.service import Document, EntityRef
from app.modules.rendering import engine
from app.modules.rendering.models import BrandingSettings
from app.modules.rendering.schemas import BrandingOut, BrandingUpdate, PaymentDefaults
from app.modules.rendering.view import BrandingView, DocType, DocumentView, PaymentInstructions
from app.platform import audit
from app.platform.deps import TenantContext

CSP = engine.CSP
DEFAULT_TEMPLATE = "classic"
LOGO_MAX_BYTES = 1024 * 1024
_LOGO_TYPES = {"image/png", "image/jpeg", "image/webp"}


class InvalidBrandingError(AppError):
    status = HTTPStatus.UNPROCESSABLE_CONTENT
    code = "invalid_branding"
    title = "Invalid branding settings"


def template_catalog() -> list[engine.TemplateManifest]:
    return list(engine.catalog().values())


async def get_branding(session: AsyncSession, tenant_id: uuid.UUID) -> BrandingSettings:
    await session.execute(
        insert(BrandingSettings).values(tenant_id=tenant_id).on_conflict_do_nothing()
    )
    return (
        await session.scalars(
            select(BrandingSettings).where(BrandingSettings.tenant_id == tenant_id)
        )
    ).one()


def branding_out(row: BrandingSettings) -> BrandingOut:
    return BrandingOut(
        templates={doc: row.templates.get(doc, DEFAULT_TEMPLATE) for doc in engine.DOC_TYPES},
        primary_color=row.primary_color,
        accent_color=row.accent_color,
        font_pair=row.font_pair,
        logo_document_id=row.logo_document_id,
        footer_text=row.footer_text,
        payment_instructions=PaymentDefaults.model_validate(row.payment_instructions),
        version=row.version,
    )


async def _check_logo(session: AsyncSession, storage: S3Storage, document_id: uuid.UUID) -> None:
    try:
        _, media_type = await documents.read_current(
            session, storage, document_id, max_bytes=LOGO_MAX_BYTES
        )
    except NotFoundError:
        raise InvalidBrandingError("Logo document not found") from None
    except AppError as exc:
        raise InvalidBrandingError(f"Logo: {exc.detail}") from None
    if media_type not in _LOGO_TYPES:
        raise InvalidBrandingError("Logo must be a PNG, JPEG or WebP image")


def _check_templates(templates: dict[str, str]) -> None:
    for doc_type, key in templates.items():
        try:
            meta = engine.manifest(key)
        except engine.UnknownTemplateError:
            raise InvalidBrandingError(f"Unknown template {key!r}") from None
        if doc_type not in meta.doc_types:
            raise InvalidBrandingError(f"Template {key!r} does not support {doc_type}")


async def update_branding(
    ctx: TenantContext, storage: S3Storage, changes: BrandingUpdate, if_match: str | None
) -> BrandingSettings:
    row = await get_branding(ctx.session, ctx.tenant_id)
    check_version(if_match, row.version)
    data = changes.model_dump(exclude_unset=True, mode="json")
    if data.get("templates"):
        _check_templates(data["templates"])
        data["templates"] = {**row.templates, **data["templates"]}
    if data.get("logo_document_id"):
        await _check_logo(ctx.session, storage, uuid.UUID(data["logo_document_id"]))
    if "payment_instructions" in data:
        data["payment_instructions"] = {
            k: v for k, v in (data["payment_instructions"] or {}).items() if v is not None
        }
    before = {f: getattr(row, f) for f in data}
    for field, value in data.items():
        setattr(row, field, uuid.UUID(value) if field == "logo_document_id" and value else value)
    row.updated_by = ctx.principal.user_id
    await ctx.session.flush()
    await ctx.session.refresh(row)
    await audit.record(
        ctx,
        "branding.updated",
        entity_type="branding",
        entity_id=row.id,
        changes=audit.diff(before, {f: getattr(row, f) for f in data}),
    )
    return row


async def branding_view(
    session: AsyncSession,
    storage: S3Storage,
    row: BrandingSettings,
    template_key: str,
    overrides: BrandingUpdate | None = None,
) -> BrandingView:
    meta = engine.manifest(template_key)
    o = overrides.model_dump(exclude_unset=True) if overrides else {}
    logo_id = o.get("logo_document_id", row.logo_document_id)
    logo_uri = None
    if logo_id is not None:
        data, media_type = await documents.read_current(
            session, storage, logo_id, max_bytes=LOGO_MAX_BYTES
        )
        if media_type in _LOGO_TYPES:
            logo_uri = f"data:{media_type};base64,{base64.b64encode(data).decode()}"
    return BrandingView(
        primary_color=o.get("primary_color") or row.primary_color or meta.default_primary,
        accent_color=o.get("accent_color") or row.accent_color or meta.default_accent,
        font_pair=cast(
            Literal["sans", "serif"], o.get("font_pair") or row.font_pair or meta.font_pair
        ),
        logo_data_uri=logo_uri,
        footer_text=o.get("footer_text", row.footer_text),
    )


def template_for(
    row: BrandingSettings, doc_type: DocType, overrides: BrandingUpdate | None = None
) -> str:
    chosen = (overrides.templates or {}) if overrides else {}
    return chosen.get(doc_type) or row.templates.get(doc_type) or DEFAULT_TEMPLATE


def with_payment_defaults(view: DocumentView, row: BrandingSettings) -> DocumentView:
    """Fill payment instructions on invoices from branding settings (keeping the document's reference)."""
    if view.doc_type != "invoice" or not row.payment_instructions:
        return view
    reference = view.payment.reference if view.payment else None
    payment = PaymentInstructions(**row.payment_instructions, reference=reference)
    return view.model_copy(update={"payment": payment})


async def render(
    renderer: PdfRenderer, template_key: str, view: DocumentView, branding: BrandingView, fmt: str
) -> bytes:
    try:
        html = engine.render_html(template_key, view, branding)
    except engine.UnknownTemplateError as exc:
        raise InvalidBrandingError(str(exc)) from None
    if fmt == "html":
        return html.encode()
    return await renderer.render(html, footer_html=engine.render_footer(view, branding))


def _render_key(template_key: str, view: DocumentView, branding: BrandingView) -> str:
    payload: dict[str, Any] = {
        "template": template_key,
        "template_version": engine.manifest(template_key).version,
        "branding": branding.model_dump(mode="json"),
        "view": view.model_dump(mode="json"),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return f"render:{digest}"


async def generate_pdf(
    session: AsyncSession,
    storage: S3Storage,
    renderer: PdfRenderer,
    *,
    tenant_id: uuid.UUID,
    view: DocumentView,
    entity: EntityRef | None,
    actor: str | None,
) -> Document:
    """Render ``view`` with the tenant's branding and store it as a document.

    Cached: the same view, template version and branding return the existing document without re-rendering,
    so re-sending an unchanged invoice costs nothing (the cache key is per *document version*).
    """
    row = await get_branding(session, tenant_id)
    key = template_for(row, view.doc_type)
    view = with_payment_defaults(view, row)
    branding = await branding_view(session, storage, row, key)
    source_key = _render_key(key, view, branding)
    if (cached := await documents.find_by_source_key(session, source_key)) is not None:
        return cached
    pdf = await render(renderer, key, view, branding, "pdf")
    title = f"{engine.DOC_TITLES[view.doc_type]} {view.number or 'draft'}"
    return await documents.store_bytes(
        session,
        storage,
        tenant_id=tenant_id,
        data=pdf,
        filename=f"{(view.number or 'draft').replace('/', '-')}.pdf",
        content_type="application/pdf",
        category="generated",
        title=title,
        source_key=source_key,
        links=[entity] if entity else None,
        actor=actor,
    )
