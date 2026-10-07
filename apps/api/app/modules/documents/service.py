"""Documents service (ADR-0023).

Upload flow: ``start_upload`` creates a *pending* version and a presigned PUT (≤ 10 min, size and type signed)
→ the client uploads straight to storage → ``complete_upload`` hashes the object, sniffs its bytes, checks the
size and extension, and only then makes the version current. Downloads are short-lived presigned GETs issued
after the permission check. Other modules store generated files with ``store_bytes``.
"""

import hashlib
import uuid
from datetime import UTC, date, datetime, timedelta
from http import HTTPStatus

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.concurrency import check_version
from app.core.config import Settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.integrations.storage.s3 import S3Storage
from app.modules.documents.models import Document, DocumentLink, DocumentVersion
from app.modules.documents.schemas import (
    DocumentCreate,
    DocumentUpdate,
    DownloadUrl,
    EntityRef,
    UploadRequest,
    UploadTicket,
)
from app.modules.documents.sniff import UnsupportedFileError, type_for_filename, verify
from app.platform import audit
from app.platform.deps import TenantContext

__all__ = ["Document", "EntityRef", "find_by_source_key", "read_current", "store_bytes"]

READY = "ready"
PENDING = "pending"


class UploadRejectedError(AppError):
    code = "upload_rejected"
    title = "The uploaded file was rejected"
    status = HTTPStatus.UNPROCESSABLE_CONTENT


class UploadMissingError(ConflictError):
    code = "upload_missing"
    title = "Nothing was uploaded for this version yet"


def _storage_key(tenant_id: uuid.UUID, document_id: uuid.UUID, version_no: int) -> str:
    # No user-controlled text in keys; the filename is only used for Content-Disposition.
    return f"t/{tenant_id}/d/{document_id}/v{version_no}/{uuid.uuid4().hex}"


def _check_upload(data: UploadRequest, settings: Settings) -> str:
    try:
        media_type = type_for_filename(data.filename).media_type
    except UnsupportedFileError as exc:
        raise UploadRejectedError(str(exc)) from None
    if data.size_bytes > settings.upload_max_bytes:
        raise UploadRejectedError(
            f"Files may be at most {settings.upload_max_bytes // (1024 * 1024)} MB"
        )
    return media_type


def _ticket(storage: S3Storage, version: DocumentVersion, settings: Settings) -> UploadTicket:
    ttl = settings.upload_url_ttl_seconds
    return UploadTicket(
        url=storage.presign_put(
            version.storage_key,
            content_type=version.content_type,
            content_length=version.size_bytes,
            ttl=ttl,
        ),
        headers={"Content-Type": version.content_type},
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl),
    )


async def _add_links(ctx: TenantContext, document_id: uuid.UUID, links: list[EntityRef]) -> None:
    if not links:
        return
    await ctx.session.execute(
        insert(DocumentLink)
        .values(
            [
                {
                    "tenant_id": ctx.tenant_id,
                    "document_id": document_id,
                    "entity_type": link.entity_type,
                    "entity_id": link.entity_id,
                    "created_by": ctx.principal.user_id,
                }
                for link in links
            ]
        )
        .on_conflict_do_nothing()
    )


async def get_document(session: AsyncSession, document_id: uuid.UUID) -> Document:
    document = await session.get(Document, document_id)
    if document is None:
        raise NotFoundError("Document not found")
    return document


async def start_upload(
    ctx: TenantContext, data: DocumentCreate, storage: S3Storage, settings: Settings
) -> tuple[Document, DocumentVersion, UploadTicket]:
    media_type = _check_upload(data, settings)
    document = Document(
        tenant_id=ctx.tenant_id,
        category=data.category,
        title=data.title or data.filename,
        expires_on=data.expires_on,
        created_by=ctx.principal.user_id,
        updated_by=ctx.principal.user_id,
    )
    ctx.session.add(document)
    await ctx.session.flush()
    version = await _new_version(ctx, document, data, media_type)
    await _add_links(ctx, document.id, data.links)
    await audit.record(
        ctx,
        "document.created",
        entity_type="document",
        entity_id=document.id,
        changes=audit.diff({}, {"category": data.category, "filename": data.filename}),
    )
    await ctx.session.refresh(document)
    return document, version, _ticket(storage, version, settings)


async def _new_version(
    ctx: TenantContext, document: Document, data: UploadRequest, media_type: str
) -> DocumentVersion:
    last = await ctx.session.scalar(
        select(func.max(DocumentVersion.version_no)).where(
            DocumentVersion.document_id == document.id
        )
    )
    version_no = (last or 0) + 1
    version = DocumentVersion(
        tenant_id=ctx.tenant_id,
        document_id=document.id,
        version_no=version_no,
        storage_key=_storage_key(ctx.tenant_id, document.id, version_no),
        filename=data.filename,
        content_type=media_type,
        size_bytes=data.size_bytes,
        created_by=ctx.principal.user_id,
    )
    ctx.session.add(version)
    await ctx.session.flush()
    return version


async def start_new_version(
    ctx: TenantContext,
    document_id: uuid.UUID,
    data: UploadRequest,
    storage: S3Storage,
    settings: Settings,
) -> tuple[Document, DocumentVersion, UploadTicket]:
    document = await get_document(ctx.session, document_id)
    media_type = _check_upload(data, settings)
    version = await _new_version(ctx, document, data, media_type)
    return document, version, _ticket(storage, version, settings)


async def _version(
    session: AsyncSession, document_id: uuid.UUID, version_no: int
) -> DocumentVersion:
    version = await session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document_id, DocumentVersion.version_no == version_no
        )
    )
    if version is None:
        raise NotFoundError("Document version not found")
    return version


def _verify_upload(version: DocumentVersion, size: int, head: bytes) -> str:
    if size != version.size_bytes:
        raise UnsupportedFileError(f"Uploaded {size} bytes but {version.size_bytes} were announced")
    return verify(version.filename, head)


async def complete_upload(
    ctx: TenantContext, document_id: uuid.UUID, version_no: int, storage: S3Storage
) -> Document:
    document = await get_document(ctx.session, document_id)
    version = await _version(ctx.session, document_id, version_no)
    if version.status == READY:
        return document  # idempotent
    if await storage.head(version.storage_key) is None:
        raise UploadMissingError()
    digest = await storage.digest(version.storage_key)
    try:
        version.content_type = _verify_upload(version, digest.size, digest.head)
    except UnsupportedFileError as exc:
        # Never keep bytes we refused. The version stays pending; the client may start a new upload.
        await storage.delete(version.storage_key)
        raise UploadRejectedError(str(exc)) from None
    version.sha256 = digest.sha256
    version.status = READY
    version.finalized_at = datetime.now(UTC)
    document.current_version_no = max(document.current_version_no or 0, version_no)
    document.updated_by = ctx.principal.user_id
    await ctx.session.flush()
    await audit.record(
        ctx,
        "document.version_uploaded",
        entity_type="document",
        entity_id=document.id,
        changes={"version_no": version_no, "sha256": digest.sha256, "size_bytes": digest.size},
    )
    await ctx.session.refresh(document)
    return document


async def store_bytes(
    session: AsyncSession,
    storage: S3Storage,
    *,
    tenant_id: uuid.UUID,
    data: bytes,
    filename: str,
    content_type: str,
    category: str,
    title: str,
    source_key: str | None = None,
    links: list[EntityRef] | None = None,
    actor: str | None = None,
) -> Document:
    """Store server-generated bytes (e.g. a rendered PDF) as a ready document. Reuses ``source_key`` hits."""
    if source_key is not None:
        existing = await session.scalar(select(Document).where(Document.source_key == source_key))
        if existing is not None:
            return existing
    document = Document(
        tenant_id=tenant_id,
        category=category,
        title=title,
        source_key=source_key,
        current_version_no=1,
        created_by=actor,
        updated_by=actor,
    )
    session.add(document)
    await session.flush()
    key = _storage_key(tenant_id, document.id, 1)
    await storage.put(key, data, content_type=content_type)
    session.add(
        DocumentVersion(
            tenant_id=tenant_id,
            document_id=document.id,
            version_no=1,
            storage_key=key,
            filename=filename,
            content_type=content_type,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            status=READY,
            created_by=actor,
            finalized_at=datetime.now(UTC),
        )
    )
    for link in links or []:
        session.add(
            DocumentLink(
                tenant_id=tenant_id,
                document_id=document.id,
                entity_type=link.entity_type,
                entity_id=link.entity_id,
                created_by=actor,
            )
        )
    await session.flush()
    return document


async def current_version(session: AsyncSession, document: Document) -> DocumentVersion:
    if document.current_version_no is None:
        raise ConflictError("This document has no uploaded file yet")
    return await _version(session, document.id, document.current_version_no)


async def download_url(
    session: AsyncSession,
    document_id: uuid.UUID,
    storage: S3Storage,
    settings: Settings,
    *,
    version_no: int | None = None,
    inline: bool = False,
) -> DownloadUrl:
    document = await get_document(session, document_id)
    version = (
        await _version(session, document_id, version_no)
        if version_no is not None
        else await current_version(session, document)
    )
    if version.status != READY:
        raise ConflictError("This version is not available")
    ttl = settings.download_url_ttl_seconds
    return DownloadUrl(
        url=storage.presign_get(
            version.storage_key,
            filename=version.filename,
            content_type=version.content_type,
            ttl=ttl,
            inline=inline,
        ),
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl),
    )


async def list_documents(
    session: AsyncSession,
    *,
    cursor: uuid.UUID | None,
    limit: int,
    entity: EntityRef | None,
    category: str | None,
    expiring_before: date | None,
    include_archived: bool,
) -> list[Document]:
    stmt = select(Document).order_by(Document.id.desc()).limit(limit + 1)
    if cursor is not None:
        stmt = stmt.where(Document.id < cursor)
    if entity is not None:
        stmt = stmt.where(
            Document.id.in_(
                select(DocumentLink.document_id).where(
                    DocumentLink.entity_type == entity.entity_type,
                    DocumentLink.entity_id == entity.entity_id,
                )
            )
        )
    if category is not None:
        stmt = stmt.where(Document.category == category)
    if expiring_before is not None:
        stmt = stmt.where(Document.expires_on <= expiring_before)
    if not include_archived:
        stmt = stmt.where(Document.status == "active")
    return list((await session.scalars(stmt)).all())


async def detail(
    session: AsyncSession, document_id: uuid.UUID
) -> tuple[Document, list[DocumentVersion], list[DocumentLink]]:
    document = await get_document(session, document_id)
    versions = (
        await session.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_no.desc())
        )
    ).all()
    links = (
        await session.scalars(select(DocumentLink).where(DocumentLink.document_id == document_id))
    ).all()
    return document, list(versions), list(links)


async def update_document(
    ctx: TenantContext, document_id: uuid.UUID, changes: DocumentUpdate, if_match: str | None
) -> Document:
    document = await get_document(ctx.session, document_id)
    check_version(if_match, document.version)
    data = changes.model_dump(exclude_unset=True)
    archived = data.pop("archived", None)
    if archived is not None:
        data["status"] = "archived" if archived else "active"
    before = {f: getattr(document, f) for f in data}
    for field, value in data.items():
        setattr(document, field, value)
    document.updated_by = ctx.principal.user_id
    await ctx.session.flush()
    await ctx.session.refresh(document)
    await audit.record(
        ctx,
        "document.updated",
        entity_type="document",
        entity_id=document.id,
        changes=audit.diff(before, {f: getattr(document, f) for f in data}),
    )
    return document


async def add_link(ctx: TenantContext, document_id: uuid.UUID, link: EntityRef) -> DocumentLink:
    await get_document(ctx.session, document_id)
    await _add_links(ctx, document_id, [link])
    row = await ctx.session.scalar(
        select(DocumentLink).where(
            DocumentLink.document_id == document_id,
            DocumentLink.entity_type == link.entity_type,
            DocumentLink.entity_id == link.entity_id,
        )
    )
    assert row is not None  # noqa: S101 - inserted or already present
    await audit.record(
        ctx,
        "document.linked",
        entity_type="document",
        entity_id=document_id,
        changes={"entity_type": link.entity_type, "entity_id": str(link.entity_id)},
    )
    return row


async def remove_link(ctx: TenantContext, document_id: uuid.UUID, link_id: uuid.UUID) -> None:
    row = await ctx.session.get(DocumentLink, link_id)
    if row is None or row.document_id != document_id:
        raise NotFoundError("Link not found")
    await ctx.session.delete(row)
    await audit.record(
        ctx,
        "document.unlinked",
        entity_type="document",
        entity_id=document_id,
        changes={"entity_type": row.entity_type, "entity_id": str(row.entity_id)},
    )


async def find_by_source_key(session: AsyncSession, source_key: str) -> Document | None:
    return await session.scalar(select(Document).where(Document.source_key == source_key))


async def read_current(
    session: AsyncSession, storage: S3Storage, document_id: uuid.UUID, *, max_bytes: int
) -> tuple[bytes, str]:
    """Bytes and media type of the current version (for small files such as logos)."""
    document = await get_document(session, document_id)
    version = await current_version(session, document)
    if version.size_bytes > max_bytes:
        raise ConflictError(f"File is larger than {max_bytes // 1024} KB")
    return await storage.get(version.storage_key), version.content_type
