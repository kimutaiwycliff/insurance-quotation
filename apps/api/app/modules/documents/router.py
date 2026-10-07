"""Document endpoints: upload (presigned), complete, list, detail, update, download, links."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response

from app.core.concurrency import etag
from app.core.pagination import Page, PageParams, build_page, page_params
from app.core.permissions import Perm
from app.modules.documents import service
from app.modules.documents.schemas import (
    DocumentCreate,
    DocumentDetail,
    DocumentLinkOut,
    DocumentOut,
    DocumentUpdate,
    DownloadUrl,
    EntityRef,
    EntityType,
    UploadRequest,
    UploadStarted,
    VersionOut,
)
from app.platform.deps import ResourcesDep, TenantContext, require_permission
from app.platform.idempotency import Idempotency, idempotency_dependency

router = APIRouter(prefix="/documents", tags=["documents"])

_read = require_permission(Perm.DOCUMENT_READ)
_write = require_permission(Perm.DOCUMENT_WRITE)
ReadCtx = Annotated[TenantContext, Depends(_read)]
WriteCtx = Annotated[TenantContext, Depends(_write)]


@router.post("", operation_id="documents_create", status_code=201, response_model=UploadStarted)
async def create_document(
    ctx: WriteCtx,
    body: DocumentCreate,
    resources: ResourcesDep,
    idem: Annotated[Idempotency, Depends(idempotency_dependency(_write))],
) -> Response:
    """Start an upload: returns a presigned PUT. Then call `.../versions/{n}/complete`."""
    if (replay := await idem.replay()) is not None:
        return replay
    document, version, ticket = await service.start_upload(
        ctx, body, resources.storage, resources.settings
    )
    out = UploadStarted(
        document=DocumentOut.model_validate(document), version_no=version.version_no, upload=ticket
    )
    return await idem.respond(201, out)


@router.post("/{document_id}/versions", operation_id="documents_new_version", status_code=201)
async def new_version(
    ctx: WriteCtx, document_id: uuid.UUID, body: UploadRequest, resources: ResourcesDep
) -> UploadStarted:
    document, version, ticket = await service.start_new_version(
        ctx, document_id, body, resources.storage, resources.settings
    )
    return UploadStarted(
        document=DocumentOut.model_validate(document), version_no=version.version_no, upload=ticket
    )


@router.post(
    "/{document_id}/versions/{version_no}/complete", operation_id="documents_complete_upload"
)
async def complete_upload(
    ctx: WriteCtx, document_id: uuid.UUID, version_no: int, resources: ResourcesDep
) -> DocumentOut:
    """Verify the uploaded bytes (size, type sniffing, SHA-256) and make the version current."""
    document = await service.complete_upload(ctx, document_id, version_no, resources.storage)
    return DocumentOut.model_validate(document)


@router.get("", operation_id="documents_list")
async def list_documents(
    *,
    ctx: ReadCtx,
    page: Annotated[PageParams, Depends(page_params)],
    entity_type: Annotated[EntityType | None, Query()] = None,
    entity_id: Annotated[uuid.UUID | None, Query()] = None,
    category: Annotated[str | None, Query(max_length=40)] = None,
    expiring_before: Annotated[date | None, Query()] = None,
    include_archived: bool = False,
) -> Page[DocumentOut]:
    entity = (
        EntityRef(entity_type=entity_type, entity_id=entity_id)
        if entity_type is not None and entity_id is not None
        else None
    )
    rows = await service.list_documents(
        ctx.session,
        cursor=page.cursor,
        limit=page.limit,
        entity=entity,
        category=category,
        expiring_before=expiring_before,
        include_archived=include_archived,
    )
    return build_page(
        [DocumentOut.model_validate(r) for r in rows], [r.id for r in rows], page.limit
    )


@router.get("/{document_id}", operation_id="documents_get")
async def get_document(ctx: ReadCtx, document_id: uuid.UUID, response: Response) -> DocumentDetail:
    document, versions, links = await service.detail(ctx.session, document_id)
    response.headers["ETag"] = etag(document.version)
    return DocumentDetail(
        **DocumentOut.model_validate(document).model_dump(),
        versions=[VersionOut.model_validate(v) for v in versions],
        links=[DocumentLinkOut.model_validate(link) for link in links],
    )


@router.patch("/{document_id}", operation_id="documents_update")
async def update_document(
    ctx: WriteCtx,
    document_id: uuid.UUID,
    body: DocumentUpdate,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
) -> DocumentOut:
    document = await service.update_document(ctx, document_id, body, if_match)
    response.headers["ETag"] = etag(document.version)
    return DocumentOut.model_validate(document)


@router.get("/{document_id}/download", operation_id="documents_download")
async def download(
    ctx: ReadCtx,
    document_id: uuid.UUID,
    resources: ResourcesDep,
    version_no: Annotated[int | None, Query(ge=1)] = None,
    inline: bool = False,
) -> DownloadUrl:
    """A short-lived presigned GET (default 5 min). Issued only after the permission check."""
    return await service.download_url(
        ctx.session,
        document_id,
        resources.storage,
        resources.settings,
        version_no=version_no,
        inline=inline,
    )


@router.post("/{document_id}/links", operation_id="documents_link", status_code=201)
async def add_link(ctx: WriteCtx, document_id: uuid.UUID, body: EntityRef) -> DocumentLinkOut:
    return DocumentLinkOut.model_validate(await service.add_link(ctx, document_id, body))


@router.delete("/{document_id}/links/{link_id}", operation_id="documents_unlink", status_code=204)
async def remove_link(ctx: WriteCtx, document_id: uuid.UUID, link_id: uuid.UUID) -> None:
    await service.remove_link(ctx, document_id, link_id)
